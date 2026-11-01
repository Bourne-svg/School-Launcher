"""Generate a local vector-inspired application icon; no network assets."""
from pathlib import Path
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parents[1]
image = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
d = ImageDraw.Draw(image)
d.rounded_rectangle((10, 10, 246, 246), 48, fill='#213b4c')
d.rounded_rectangle((54, 57, 202, 199), 13, fill='#d8ebe0')
d.rounded_rectangle((46, 48, 193, 190), 12, fill='#ffffff')
d.rectangle((67, 71, 78, 165), fill='#18796e')
d.rounded_rectangle((96, 78, 167, 87), 3, fill='#213b4c')
d.rounded_rectangle((96, 107, 157, 116), 3, fill='#76958a')
d.rounded_rectangle((96, 136, 146, 145), 3, fill='#76958a')
image.save(root / 'ui' / 'app.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
print('Icon generated')
from sys import path
path.insert(0,str(root))
from autofill import extension_id
(root/'extension'/'id.txt').write_text(extension_id()+'\n',encoding='utf-8')
image.resize((128,128)).save(root/'extension'/'icon.png')
