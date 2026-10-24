"""Local, rectangular Aura Archive presentation. Existing aura logic lives elsewhere."""
from __future__ import annotations

from functools import lru_cache
from hashlib import sha256
from io import BytesIO
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps
from bot.services.card_renderer import font

SIZE=(1500,1000)
PORTRAIT=(98,182,540)


@lru_cache(maxsize=24)
def _serif(size):
    for path in ('C:/Windows/Fonts/georgia.ttf','/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf'):
        if Path(path).is_file():
            return ImageFont.truetype(path,size)
    return font(size)


def _text(draw,box,value,size,color,*,minimum=20,serif=True):
    x,y,width,height=box
    value=' '.join(str(value).split())[:180]
    def wrap(chosen):
        rows=[]; row=''
        for word in value.split():
            candidate=(row+' '+word).strip()
            if row and draw.textlength(candidate,font=chosen)>width:
                rows.append(row);row=word
            else:
                row=candidate
        return rows+[row]
    # Use the general font for names outside the serif's common script range.
    family=_serif if serif and all(ord(char)<0x3000 for char in value) else font
    while True:
        chosen=family(size)
        rows=wrap(chosen)
        if size<=minimum or (len(rows)*(size+7)<=height and all(draw.textlength(row,font=chosen)<=width for row in rows)):
            break
        size-=1
    count=max(1,height//(size+7))
    rows=rows[:count]
    for index,row in enumerate(rows):
        while row and draw.textlength(row,font=chosen)>width:
            row=row[:-2]+'…'
        draw.text((x,y+index*(size+7)),row,font=chosen,fill=color)


def _spark(draw,x,y,r,color):
    points=[]
    for i in range(8):
        a=i*math.pi/4; radius=r if i%2==0 else r*.22
        points.append((x+math.sin(a)*radius,y+math.cos(a)*radius))
    draw.polygon(points,fill=color)


def _flower(draw,x,y,r,color):
    for index in range(5):
        a=index*math.tau/5
        points=[]
        for sign,steps in ((-1,range(11)),(1,range(10,-1,-1))):
            for step in steps:
                t=step/10; px=sign*math.sin(math.pi*t)*r*.34; py=-t*r
                points.append((x+px*math.cos(a)-py*math.sin(a),y+px*math.sin(a)+py*math.cos(a)))
        draw.polygon(points,fill=color)
    draw.ellipse((x-3,y-3,x+3,y+3),fill='#e4a6b9')


@lru_cache(maxsize=1)
def _frame():
    # No user content enters the shared frame. Callers always copy it.
    strip=Image.new('RGB',(1,SIZE[1]))
    strip.putdata([(int(32-14*math.sin(y/SIZE[1]*math.pi)),
                    int(23-10*math.sin(y/SIZE[1]*math.pi)),
                    int(32-10*math.sin(y/SIZE[1]*math.pi))) for y in range(SIZE[1])])
    image=strip.resize(SIZE).convert('RGBA')
    draw=ImageDraw.Draw(image)
    draw.rounded_rectangle((26,25,1474,975),radius=24,outline='#c593aa',width=2)
    # Delicate vines and blossoms are kept around the outer margins.
    for mirror in (False,True):
        def xy(x,y):
            return (1500-x,y) if mirror else (x,y)
        branch=[xy(x,y) for x,y in ((26,170),(78,220),(48,310),(70,430),(34,555),(68,686),(35,783),(70,913))]
        draw.line(branch,fill='#53303f',width=2)
        for x,y,r in ((42,188,25),(62,295,20),(31,552,31),(55,700,28),(78,899,32)):
            xx,yy=xy(x,y); _flower(draw,xx,yy,r,'#4d2a3c')
    for i in range(40):
        x=55+(i*193)%1380; y=140+(i*127)%585
        if 690<x<1445 and y>300:
            continue
        if i%4==0:
            _spark(draw,x,y,3,'#ae6c89')
        else:
            draw.ellipse((x,y,x+1,y+1),fill='#7f536b')
    _flower(draw,81,78,25,'#efa0b1')
    draw.line((641,73,800,73),fill='#a97a8c',width=1)
    _spark(draw,641,73,4,'#f0bac5');_spark(draw,800,73,4,'#f0bac5')
    draw.arc((1040,25,1470,180),185,325,fill='#603449',width=1)
    draw.arc((1075,-35,1470,130),20,135,fill='#603449',width=1)
    return image


def _asset(data):
    if not data:
        return None
    try:
        with Image.open(BytesIO(data)) as source:
            if source.width*source.height>4_000_000:
                return None
            source.thumbnail((1024,1024),Image.Resampling.LANCZOS)
            return source.convert('RGBA')
    except (OSError,ValueError,Image.DecompressionBombError):
        return None


def _portrait(image,visual):
    x,y,size=PORTRAIT
    art=_asset(visual.avatar)
    if art is None:
        art=Image.new('RGBA',(size,size),'#543648')
        ImageDraw.Draw(art).text((size/2,size/2),visual.name[:1] or '?',font=_serif(140),anchor='mm',fill='#fcebdc')
    art=ImageOps.fit(art,(size,size),method=Image.Resampling.LANCZOS)
    mask=Image.new('L',(size,size))
    ImageDraw.Draw(mask).ellipse((0,0,size-1,size-1),fill=255)
    image.paste(art,(x,y),mask)
    decoration=_asset(visual.decoration)
    if decoration is not None:
        decoration=ImageOps.contain(decoration,(size+38,size+38),Image.Resampling.LANCZOS)
        image.alpha_composite(decoration,(x+(size-decoration.width)//2,y+(size-decoration.height)//2))
    draw=ImageDraw.Draw(image)
    for pad,color,width in ((7,'#ecaab9',3),(24,'#ddb1b4',2),(38,'#653a4b',1)):
        draw.ellipse((x-pad,y-pad,x+size+pad,y+size+pad),outline=color,width=width)
    for xx,yy,r in ((x+size/2,y-24,19),(x+size/2,y+size+25,17),(x-22,y+size/2,8),(x+size+23,y+size/2,8)):
        _spark(draw,xx,yy,r,'#f3c7b9')
    for xx,yy,r in ((108,276,24),(93,638,22),(170,722,17)):
        _flower(draw,xx,yy,r,'#e1a0ad')


def _panel(draw,box):
    draw.rounded_rectangle(box,radius=19,fill='#1b1420',outline='#79516b',width=1)


def _icon(draw,index,x,y):
    pink='#f0a8bc'
    if index==0:
        draw.polygon([(x-17,y-7),(x-9,y-17),(x+9,y-17),(x+17,y-7),(x,y+13)],outline=pink,width=3)
        draw.line((x-17,y-7,x+17,y-7),fill=pink,width=2)
        draw.line((x-9,y-17,x,y+13,x+9,y-17),fill=pink,width=2)
    elif index==1:
        draw.polygon([(x,y-22),(x+7,y-5),(x+15,y+5),(x+11,y+18),(x,y+22),(x-11,y+18),(x-15,y+5),(x-5,y-8)],fill=pink)
        draw.ellipse((x-5,y+3,x+5,y+18),fill='#1b1420')
    elif index==2:
        _spark(draw,x,y,19,'#f5d0bd')
    else:
        draw.line((x,y-24,x,y+22),fill=pink,width=4)
        draw.polygon([(x,y-27),(x-5,y-15),(x+5,y-15)],fill=pink)
        draw.line((x-12,y+5,x+12,y+5),fill=pink,width=3)
        _spark(draw,x,y+22,6,'#f4cfbd')


def render_archive(visual,*,title,energy,traits,affinity,class_name):
    image=_frame().copy()
    draw=ImageDraw.Draw(image)
    draw.text((132,48),'MEYAYA / AURA ARCHIVE',font=_serif(32),fill='#fff0e8')
    draw.text((133,98),'P R O F I L E  ·  A E S T H E T I C  ·  E S S E N C E  ·  S I G N A T U R E',font=font(15),fill='#cfb8c9')
    monogram=''.join(word[:1] for word in title.split())[:3].upper()
    code=int.from_bytes(sha256(('aura-code:'+visual.asset_fingerprint).encode()).digest()[:4],'big')%100000
    draw.text((1405,55),'P R O F I L E  C O D E',font=font(14),anchor='ra',fill='#bc9bae')
    draw.text((1405,80),f'#{monogram}-{code:05d}',font=_serif(25),anchor='ra',fill='#efa5b6')
    _spark(draw,1443,77,14,'#f7c5bf')
    _portrait(image,visual)
    draw=ImageDraw.Draw(image)
    _text(draw,(696,159,545,100),visual.name,84,'#fff5ee',minimum=38)
    draw.line((699,256,1225,256),fill='#9f6b80',width=1)
    _spark(draw,1228,256,13,'#efb8c2')
    draw.text((699,271),'P R O F I L E - B O R N  E S S E N C E',font=font(14),fill='#c99dad')
    # Monogram colour echoes the measured palette, with a light readable border.
    draw.ellipse((1280,154,1408,282),fill=visual.palette[0],outline='#edb2bf',width=3)
    draw.ellipse((1287,161,1401,275),outline='#9c6c83',width=1)
    draw.text((1344,219),monogram,font=_serif(43 if len(monogram)<3 else 34),anchor='mm',fill='#fff0e4',stroke_width=1,stroke_fill='#694557')
    boxes=((696,304,1444,402),(696,416,1444,536),(696,550,1444,638),(696,652,1444,742))
    headings=('A U R A  A R C H E T Y P E','E S S E N C E','S I G N A T U R E','A F F I N I T Y')
    contents=(title.upper(),energy,traits.replace('•','·'),f'{affinity.upper()} AFFINITY · {class_name.upper()}')
    for index,(box,heading,content) in enumerate(zip(boxes,headings,contents)):
        _panel(draw,box)
        if index in (0,3):
            draw.arc((1320,box[1]-20,1460,box[3]+25),105,255,fill='#482b3f',width=1)
            _flower(draw,1428,box[3]-10,30,'#362333')
        _icon(draw,index,741,(box[1]+box[3])//2)
        draw.text((801,box[1]+15),heading,font=font(14),fill='#cfb5c9')
        size=(33,29,28,24)[index]
        height=box[3]-box[1]-42
        _text(draw,(801,box[1]+42,615,height),content,size,'#f1a6b5' if index in (0,3) else '#f5e8ee',minimum=20)
    _panel(draw,(56,768,1444,938))
    _spark(draw,105,851,19,'#f7c9bb')
    draw.text((168,821),'P R O F I L E - B O R N',font=font(17),fill='#cdb0c4')
    draw.text((168,855),'C O L O R  S I G N A T U R E',font=font(16),fill='#cdb0c4')
    for index,color in enumerate(visual.palette[:5]):
        x=478+index*156
        draw.rounded_rectangle((x,794,x+136,876),radius=13,fill=color,outline='#dbacb8',width=1)
    draw.line((170,905,442,905),fill='#a66c83',width=1)
    _spark(draw,170,905,3,'#e4b0bf');_spark(draw,442,905,4,'#bd87a4')
    draw.text((960,905),'EST. FROM AVATAR · BANNER · PROFILE ELEMENTS',font=font(11),anchor='ma',fill='#b397ac')
    _spark(draw,1404,905,8,'#edb4c4')
    return image
