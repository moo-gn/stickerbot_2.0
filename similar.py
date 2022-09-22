import imagehash
from PIL import Image

# Parameters: image in BytesIO, path for hashes to check, cutoff default = 15, minimum bit differenxe
# Returns: most similar image's path if it exists, if not returns False
def is_similar(source_img, cursor, cutoff=15, table = 'stickers'):

    # Convert BytesIO to PIL
    source_img = Image.open(source_img)

    # Fix transparency issue
    source_img = source_img.convert('RGB')

    # Get hash of source img
    hash0 = imagehash.average_hash(source_img) 

    # Target hashes to compare against
    cursor.execute(f"SELECT link, id, label FROM {table};")
    data = cursor.fetchall()

    # Iterate through all images in db
    for link, hash, name in data:
        
        # Unpack value
        hash1 = imagehash.hex_to_hash(hash)

        # maximum bits that could be different between the hashes. 
        if hash0 - hash1 < cutoff:
            return link, str(hash0), name
    
    # No similar image found
    return False, str(hash0)