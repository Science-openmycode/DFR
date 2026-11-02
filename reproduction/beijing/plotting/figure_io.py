import hashlib
import json
from pathlib import Path
from PIL import Image, ImageDraw
ROOT=Path(__file__).resolve().parents[1]

def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))

def sha(path):
    with Path(path).open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()

def pair(left,right,path,labels):
    a=Image.open(left).convert('RGB');b=Image.open(right).convert('RGB')
    width=max(a.width,b.width); a=a.resize((width,round(a.height*width/a.width)));b=b.resize((width,round(b.height*width/b.width)))
    canvas=Image.new('RGB',(2*width+40,max(a.height,b.height)+70),'white')
    canvas.paste(a,(0,70));canvas.paste(b,(width+40,70))
    pen=ImageDraw.Draw(canvas);pen.text((15,20),labels[0],fill='black');pen.text((width+55,20),labels[1],fill='black');canvas.save(path)
