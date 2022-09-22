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
bot = commands.Bot(command_prefix=[commands.bot.when_mentioned,'\u200b'], case_insensitive = True, intents=discord.Intents.all())

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
def removeemoji(name, delete = True):

    #DB Init
    cursor, db = db_init()

    #SAVE INFORMATION
    cursor.execute(f"SELECT link, id, uses FROM {table} WHERE label='{name}';")
    data = cursor.fetchall()

    #DELETE ENTRY
    if delete:
        cursor.execute(f"DELETE FROM {table} WHERE label='{name}';")
        db.commit()

    #DB CLOSE
    db.close()

    #RETURN LINK ID AND USES
    return data[0]

#adds emoji to the json file after checking the hash similarity
async def addemoji(url,message):
    #DB Init
    cursor, db = db_init()

    if url.lower().endswith(('.png', '.gif','.webp','.jpg','.jpeg')):
        response = requests.get(url)
        imghash = is_similar(BytesIO(response.content),cursor,cutoff=9)

        #CLOSE DB
        db.close()

        view = confirm('check the list next time')
        if imghash[0]:
            try:
                embed = discord.Embed(title=f"this looks similar to ;{imghash[2]}, you still wanna add it?")
                embed.set_image(url = imghash[0])
                await message.reply(embed = embed,  view = view)
                if await view.wait():
                    return
            except Aborted:
                return 
        
        if len(message.content.split(' ')) > 2:
            name = message.content.split(' ')[2]
            await message.reply(content = 'choose emoji filter',  view = chooseFilter(name,[url, imghash[1]]))
        else:
            msgb = await message.reply('reply to this message with the name')
            try:
                msg = await bot.wait_for('message', check = lambda i : i.reference.message_id == msgb.id)
                name = msg.content.lower()
            except AttributeError:
                await msgb.edit('Aborted no reply')
                return
            await msgb.edit(content = 'choose emoji filter',  view = chooseFilter(name,[url, imghash[1]]))
        
    else:
        await message.reply('only images and GIFs')
    
#renames emoji from file and json
async def renameemoji(message):
    name = message.content.split(' ')[-2]
    newname = message.content.split(' ')[-1]
    content = removeemoji(name, delete = False)
    view = chooseFilter(newname, content[:2], content[2])
    await message.channel.send(content = 'done renaming',  view = view)
    if await view.wait():
        return
    removeemoji(name)


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
                #DB Init
                cursor, db = db_init()
                #prompt user to confirm replacment
                view = confirm('Aborted')
                embed = discord.Embed(title=f"you sure you wanna replace the current ;{self.name}?")
                embed.set_image(url = emojis(self.name, increment=False))
                await interaction.response.edit_message(embed = embed,  view = view)
                if await view.wait():
                    return
                #replace database entry
                cursor.execute(f"REPLACE INTO {table}(label, category, uses, id, link) values ('{self.name}', '{select.values[0]}', {self.uses}, '{self.content[1]}', '{self.content[0]}');")            
                db.commit()
                #CLOSE DB
                db.close()
                #followup message
                self.stop()
                await interaction.followup.send(content='done')
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
        await interaction.message.delete()
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


#main events

@bot.event
async def on_ready():
    print('We have logged in as {0.user}'.format(bot) + ' ' + datetime.datetime.utcnow().strftime("%m/%d/%Y %H:%M:%S UTC"))

@bot.event
async def on_message(message):

    message.content = message.content.lower()
    if message.author == bot.user:
            return
    
    #main command to fetch emoji using prefix

    prefix = ';'
    if prefix in message.content:
        msg = message.content.split()
        for word in msg:
            if word.startswith(prefix):
                name = word.strip(prefix)
                break
        try:
            await message.channel.send(content = emojis(name))
        except IndexError:
            #DB Init
            cursor, db = db_init()
            cursor.execute(f"SELECT label FROM {table};")
            #CLOSE DB
            db.close()
            data = [item[0] for item in cursor.fetchall()]
            match = difflib.get_close_matches(name, data, n=1, cutoff=0.6)
            if match:
                await message.channel.send(content = f'did you mean ;{match[0]} ?', view = autocorrect(match[0]))
            else:
                await message.channel.send(content ='https://cdn.discordapp.com/attachments/901393528364621865/901616614812811274/npcmeme.png', delete_after=1)

    #checks if mentioned for the admin commands

    elif bot.user.mentioned_in(message):
    
        #list command

        if message.content.startswith('list') or message.content.endswith('list'):
            await message.channel.send(view = menu(1), embed = emojilist(1))
    
        #add command

        elif 'add' in message.content.split(' ') and message.content.split(' ').index('add') == 1:
            msg = message
            # Added this line to fetch reply content if it exists
            if message.reference:
                msg = await message.channel.fetch_message(message.reference.message_id)

            if len(msg.attachments) == 0:
                await message.reply(content ='no attachment dickhead')
            else:
                await addemoji(msg.attachments[0].url,message)     
    
        #remove command

        elif 'remove' in message.content.split(' '):    
                try:
                    #prompt user to confirm delete process
                    name = message.content.split(' ')[-1]
                    view = confirm('Aborted')
                    embed = discord.Embed(title=f"you sure you wanna delete ;{name}?")
                    embed.set_image(url = emojis(name, increment= False))
                    msg = await message.reply(embed = embed,  view = view)
                    if await view.wait():
                        return
                    removeemoji(name)
                    await message.reply(content = 'get it outta here')
                except Aborted:
                    return
                except IndexError:
                    await message.channel.send(content ='https://cdn.discordapp.com/attachments/901393528364621865/901616614812811274/npcmeme.png', delete_after=1)
    
        #rename command

        elif 'rename' in message.content.split(' '):
                try:
                    #prompt user to confirm rename process
                    name = message.content.split(' ')[-2]
                    newname = message.content.split(' ')[-1]
                    view = confirm('Aborted')
                    embed = discord.Embed(title=f"you sure you wanna rename ;{name} to ;{newname}?")
                    embed.set_image(url = emojis(name, increment=False))
                    msg = await message.reply(embed = embed,  view = view)
                    if await view.wait():
                        return
                    await renameemoji(message)
                except Aborted:
                    return
                except IndexError:
                    await message.channel.send(content ='https://cdn.discordapp.com/attachments/901393528364621865/901616614812811274/npcmeme.png', delete_after=1)
    
        #pleasantries

        elif message.content.startswith('hello') or message.content.endswith('hello'):
            await message.reply(content ='Hi')

bot.run(credentials.Captain_Bot)