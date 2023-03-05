import discord
from discord.ext import commands
import requests
from io import BytesIO
import difflib
from pymysql import connect, IntegrityError
from sshtunnel import SSHTunnelForwarder
import datetime

from similar import is_similar

import sys
sys.path.append("..")
import credentials

table = 'stickers'
bot = commands.Bot(case_insensitive = True, intents=discord.Intents.all())

# start the connection to pythonanywhere
connection = SSHTunnelForwarder((credentials.ssh_website),
                                ssh_username=credentials.ssh_username, ssh_password=credentials.ssh_password,
                                remote_bind_address=(credentials.remote_bind_address, 3306),
                             ) 
connection.start()

def db_init():
  """
  Connects to the remote database, returns the database and its cursor
  """
  # Connect
  db = connect(
      user=credentials.db_user,
      passwd=credentials.db_passwd,
      host=credentials.db_host, port=connection.local_bind_port,
      db=credentials.db,
  )

  # Return cursor and db
  return db.cursor(), db 

#check for permission
async def checkrole(msg, roles = []):
    if [y.id for y in msg.author.roles if y.id in roles]:
        return True
    else:
        await msg.reply(content ='nice try, no privilege')
        return False

#returns a url from json of emoji Name
def emojis(name, increment = True):

    #DB Init
    cursor, db = db_init()

    #RETRIEVE LINK
    cursor.execute(f"SELECT link FROM {table} WHERE label='{name}';")
    data = cursor.fetchall()

    #UPDATE USE IF INCREMENT IS TRUE
    if increment:
        cursor.execute(f"UPDATE {table}  SET uses=uses+1 WHERE label='{name}';")
        db.commit()

    #CLOSE DB
    db.close()

    #RETURN LINK
    return data[0][0]

#autocomplete context for sticker slash command options
async def autocomplete(ctx: discord.AutocompleteContext):
    cursor, db = db_init()
    if ctx.value:
        cursor.execute(f"SELECT label FROM {table};")
    else: cursor.execute(f"SELECT label FROM {table} ORDER BY uses DESC LIMIT 25;")
    db.close()
    data = [item[0] for item in cursor.fetchall()]
    if not ctx.value: data.sort()
    match = difflib.get_close_matches(ctx.value, data, n=5, cutoff=0.6)
    starts = [i for i in data if i.startswith(ctx.value)]
    results = []
    if starts:
       results.extend(starts)
    if match:
        match = [i for i in match if i not in starts]
        results.extend(match)
    return results


#list emoji page and takes filter returns an embed with emojis names as fields
def emojilist(page, filter = None):
    emojilist.page = page
    listembed = discord.Embed(title = 'Emoji List', color=0x949597)
    listembed.set_thumbnail(url ='https://cdn.discordapp.com/attachments/899467150056640546/901029776033218570/Layer_0.png')
    
    #DB Init
    cursor, db = db_init()

    if filter == 'favourites':
        #RETRIEVE TOP USES EMOJIS
        cursor.execute(f"SELECT label FROM {table} ORDER BY uses DESC LIMIT 25;")
        data = [item[0] for item in cursor.fetchall()]
    elif filter:
        #RETRIEVE DATA WITH SPECIFIC FILTER
        cursor.execute(f"SELECT label FROM {table} WHERE category='{filter}';")
        data = [item[0] for item in cursor.fetchall()]
    else:
        #RETRIEVE ALL DATA
        cursor.execute(f"SELECT label FROM {table};")
        data = [item[0] for item in cursor.fetchall()]

    #CLOSE THE DB
    db.close()

    pages = -(-len(data)//25)
    listembed.set_footer(text = '{0}/{1}'.format(page, pages) )
    for i in range((page - 1)*25,len(data)):
        listembed.add_field(name=(data[i]), value = '\u200b' , inline=True)
    return listembed

#get page numbers
def pages(filter = None):

    #DB Init
    cursor, db = db_init()

    if filter:
        #RETRIEVE DATA WITH SPECIFIC FILTER
        cursor.execute(f"SELECT label FROM {table} WHERE category='{filter}';")
        data = [item[0] for item in cursor.fetchall()]
    else:
        #RETRIEVE ALL DATA
        cursor.execute(f"SELECT label FROM {table};")
        data = [item[0] for item in cursor.fetchall()]

    #CLOSE THE DB
    db.close()

    #RETURN LENGTH
    return -(-len(data)//25)

#remove name from json file and returns url
def removeemoji(name):

    #DB Init
    cursor, db = db_init()

    #DELETE ENTRY
    cursor.execute(f"DELETE FROM {table} WHERE label='{name}';")
    db.commit()

    #DB CLOSE
    db.close()

#adds emoji to the json file after checking the hash similarity
async def addemoji(url,ctx, name):
    #DB Init
    cursor, db = db_init()

    if url.lower().endswith(('.png', '.gif','.webp','.jpg','.jpeg')):
        response = requests.get(url)
        imghash = is_similar(BytesIO(response.content),cursor,cutoff=9)

        #CLOSE DB
        db.close()

        view = confirm('check the list next time')
        msg = None
        if imghash[0]:
            try:
                embed = discord.Embed(title=f"this looks similar to {imghash[2]}, you still wanna add it?")
                embed.set_image(url = imghash[0])
                msg = await ctx.followup.send(embed = embed,  view = view, wait = True)
                if await view.wait():
                    return
            except Aborted:
                return 
        if msg:
            await msg.edit(content = 'choose emoji filter',  view = chooseFilter(name,[url, imghash[1]]))
        else:
            await ctx.followup.send(content = 'choose emoji filter',  view = chooseFilter(name,[url, imghash[1]]))
    else:
        await ctx.followup.send('only images and GIFs')
    
#renames emoji from file and json
async def renameemoji(msg ,name , newname):
    cursor, db = db_init()
    cursor.execute(f"SELECT link, id, uses, category FROM {table} WHERE label='{name}';")
    content = cursor.fetchall()[0]
    #DB Init
    #INSERT NEW ENTRY TO DATABASE
    cursor.execute(f"INSERT INTO {table}(label, category, uses, id, link) values ('{newname}', '{content[3]}', {content[2]}, '{content[1]}', '{content[0]}');")            
    db.commit()
    #CLOSE DB
    db.close()
    #MSG FINISHED WITH ADDING
    await msg.edit(content = 'done renaming')
    removeemoji(name)

async def recat(msg, name,link,id,uses):
    view = chooseFilter(name, (link, id), uses)
    await msg.edit(content = 'choose a new category',  view = view)
    removeemoji(name)
    await msg.edit(content = 'done recategorizing')
    

#VIEWS VIEW VIEWS----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# view which initialize component part of the list function
class menu(discord.ui.View):
    def __init__(self, page, filter = None):
        super().__init__(timeout=None)
        self.page = page
        self.filter = filter

    options = [
            discord.SelectOption(label='all', description='display all emotes'),
            discord.SelectOption(label='homebrew', description='our homebrewn emotes', emoji='🏠'),
            discord.SelectOption(label='internet', description='emotes from the net', emoji= '🌐' ),
            discord.SelectOption(label='favourites', description='most used emojis', emoji= '⭐' )
        ]
    @discord.ui.select(placeholder='choose filter to limit results', min_values=1, max_values=1, options=options)
    async def dropdown(self, select: discord.ui.select, interaction: discord.Interaction):
        if select.values[0] == 'all':
            self.filter = None
        else:
            self.filter = select.values[0]
        await interaction.response.edit_message(embed = emojilist(1, filter=self.filter), view = menu(1,self.filter))

    @discord.ui.button(label='prev', style=discord.ButtonStyle.grey)
    async def prev(self, button: discord.ui.Button, interaction: discord.Interaction):
        if self.page > 1:
            page = (self.page - 1)
        else:
            page = self.page
        await interaction.response.edit_message(embed = emojilist(page, filter=self.filter), view = menu(page,self.filter))
        
    @discord.ui.button(label='next', style=discord.ButtonStyle.grey)
    async def next(self, button: discord.ui.Button, interaction: discord.Interaction):
        if self.page < pages(self.filter) and not self.filter == 'favourites':
            page = (self.page + 1) 
        else:
            page = self.page
        await interaction.response.edit_message(embed = emojilist(page,filter=self.filter), view = menu(page,self.filter))


# a view that adds name to json dict from a list

class chooseFilter(discord.ui.View):
    def __init__(self, name, content, uses=0 ):
        super().__init__()
        self.name = name
        self.content = content
        self.uses = uses

    options = [
            discord.SelectOption(label='homebrew', description='our homebrewn emotes', emoji='🏠'),
            discord.SelectOption(label='internet', description='emotes from the net', emoji= '🌐' )
        ]
    @discord.ui.select(placeholder='Set filter', min_values=1, max_values=1, options=options)
    async def dropdown(self, select: discord.ui.select, interaction: discord.Interaction):
        msg_id = interaction.message.id
        try:
            #DB Init
            cursor, db = db_init()
            #INSERT NEW ENTRY TO DATABASE
            cursor.execute(f"INSERT INTO {table}(label, category, uses, id, link) values ('{self.name}', '{select.values[0]}', {self.uses}, '{self.content[1]}', '{self.content[0]}');")            
            db.commit()
            #CLOSE DB
            db.close()
            #MSG FINISHED WITH ADDING
            self.stop()
            await interaction.response.edit_message(content='done', view = self.clear_items())
        #if duplicate name this error will raise
        except IntegrityError:
            try:
                db.close()
                #prompt user to confirm replacment
                view = confirm('Aborted')
                embed = discord.Embed(title=f"you sure you wanna replace the current ;{self.name}?")
                embed.set_image(url = emojis(self.name, increment=False))
                await interaction.response.edit_message(embed = embed,  view = view)
                if await view.wait():
                    return
                #DB Init
                cursor, db = db_init()
                #replace database entry
                cursor.execute(f"REPLACE INTO {table}(label, category, uses, id, link) values ('{self.name}', '{select.values[0]}', {self.uses}, '{self.content[1]}', '{self.content[0]}');")            
                db.commit()
                #CLOSE DB
                db.close()
                #followup message
                self.stop()
                await interaction.followup.edit_message(msg_id, content='done')
            except Aborted:
                return


class Aborted(Exception):
    pass

#confirm to bypass the Aborted or abort

class confirm(discord.ui.View):
    def __init__(self, msg):
        super().__init__(timeout=None)
        self.msg = msg

    @discord.ui.button(label='YES', style=discord.ButtonStyle.green)
    async def yes(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.message.edit(content = "thinking..", embed=None, view=None)
        self.stop()
    @discord.ui.button(label='NO', style=discord.ButtonStyle.red)
    async def no(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.message.edit(content= self.msg, embed=None, view = self.clear_items())
        raise Aborted

#confirm suggested  auto correction to send emoji or abort

class autocorrect(discord.ui.View):
    def __init__(self, name):
        super().__init__(timeout=None)
        self.name = name

    @discord.ui.button(label='YES', style=discord.ButtonStyle.green)
    async def yes(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.message.edit(content=emojis(self.name), view = self.clear_items())

    @discord.ui.button(label='NO', style=discord.ButtonStyle.red)
    async def no(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.message.delete()

#VIEWS VIEW VIEWS ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------     

#slash commands -----------------------------------------------------------------------------------------------------------

#sticker fetch
@bot.slash_command(guild_ids=[credentials.guild_id] , description="fetch a sticker")
async def sticker(ctx :discord.context, name : discord.Option(str, autocomplete=autocomplete), msg: discord.Option(str, "Enter your friend's name", required = False, default = '')):
    try:
        await ctx.defer()
        name = emojis(name)
        encoding = name.split('.')[-1]
        response = requests.get(name)
        await ctx.followup.send(content = msg, file = discord.File(BytesIO(response.content), f"{name}.{encoding}"))
    except IndexError:
        await ctx.respond(content ='https://cdn.discordapp.com/attachments/901393528364621865/901616614812811274/npcmeme.png', delete_after=2)

#list stickers
@bot.slash_command(guild_ids=[credentials.guild_id] , description="list stickers")
async def list(ctx :discord.context):
        await ctx.defer()
        await ctx.followup.send(view = menu(1), embed = emojilist(1))


#add sticker
@bot.slash_command(guild_ids=[credentials.guild_id] , description="add a sticker")
async def add(ctx :discord.context,file: discord.Attachment, name : str):
    await ctx.defer()
    await addemoji(file.url,ctx, name)    


#delete a sticker
@bot.slash_command(guild_ids=[credentials.guild_id] , description="delete a sticker")
async def remove(ctx :discord.context, name : str):
    await ctx.defer()
    try:
        #prompt user to confirm delete process
        view = confirm('Aborted')
        embed = discord.Embed(title=f"you sure you wanna delete {name}?")
        embed.set_image(url = emojis(name, increment= False))
        msg = await ctx.followup.send(embed = embed,  view = view, wait= True)
        if await view.wait():
            return
        removeemoji(name)
        await msg.edit(content = 'get it outta here')
    except Aborted:
        return
    except IndexError:
        await ctx.followup.send(content ='https://cdn.discordapp.com/attachments/901393528364621865/901616614812811274/npcmeme.png', delete_after=2)   


#rename a sticker
@bot.slash_command(guild_ids=[credentials.guild_id] , description="rename a sticker")
async def rename(ctx :discord.context, name : str, newname:str):
    await ctx.defer()
    try:
        view = confirm('Aborted')
        embed = discord.Embed(title=f"you sure you wanna rename {name} to {newname}?")
        embed.set_image(url = emojis(name, increment=False))
        msg = await ctx.followup.send(embed = embed,  view = view)
        if await view.wait():
            return
        await renameemoji(msg,name,newname)
    except Aborted:
        return
    except IndexError:
        await ctx.followup.send(content ='https://cdn.discordapp.com/attachments/901393528364621865/901616614812811274/npcmeme.png', delete_after=2)

@bot.slash_command(guild_ids=[credentials.guild_id] , description="recatogrize a sticker")
async def recategorize(ctx :discord.context, name : str):
    await ctx.defer()
    cursor, db = db_init()
    cursor.execute(f"SELECT link, id, uses, category FROM {table} WHERE label='{name}';")
    content = cursor.fetchall()[0]
    db.close()
    try:
        view = confirm('Aborted')
        embed = discord.Embed(title=f"you sure you wanna recatogrize {name} from {content[3]}?")
        embed.set_image(url = emojis(name, increment=False))
        msg = await ctx.followup.send(embed = embed,  view = view)
        if await view.wait():
            return
        await recat(msg,name,content[0],content[1],content[2])
    except Aborted:
        return
    except IndexError:
        await ctx.followup.send(content ='https://cdn.discordapp.com/attachments/901393528364621865/901616614812811274/npcmeme.png', delete_after=2)


#say hello
@bot.slash_command(guild_ids=[credentials.guild_id] , description="say hi")
async def hello(ctx :discord.context):
    await ctx.defer()
    await ctx.followup.send(content ='Hi')


#login event
@bot.event
async def on_ready():
    print('We have logged in as {0.user}'.format(bot) + ' ' + datetime.datetime.utcnow().strftime("%m/%d/%Y %H:%M:%S UTC"))

bot.run(credentials.Captain_Moji)