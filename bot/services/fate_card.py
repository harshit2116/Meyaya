"""Archetype-specific illustrated Fate cards with bounded local rendering."""
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from PIL import Image,ImageDraw,ImageFilter,ImageOps
from bot.services.aura_archive import _asset,_serif,_text
from bot.services.card_renderer import font

SIZE=(1421,1107)
ASSETS=Path(__file__).resolve().parents[1]/'assets'/'celestial'/'fate'
INK='#19212a'
GOLD='#b28a61'
PALE='#f7eddd'
SCENES={
    'The Wanderer':('wanderer','SOME ROADS ARE MEANT TO BE WANDERED'),
    'The Crownless King':('king','A CROWN IS NOT WHAT MAKES A LEADER'),
    'The Last Witness':('witness','SOME TRUTHS WAIT FOR A QUIET MOMENT'),
    'The Trickster':('trickster','THE UNEXPECTED CAN OPEN A NEW DOOR'),
}


def _veil(image,box,color,opacity):
    x,y,right,bottom=box
    # Blur only a small alpha mask. Keeping RGB constant avoids grey halos
    # around pale reading surfaces and processing full-card buffers.
    padding=36
    size=(right-x+padding*2,bottom-y+padding*2)
    mask=Image.new('L',size)
    ImageDraw.Draw(mask).rounded_rectangle((padding,padding,size[0]-padding,size[1]-padding),
                                           radius=12,fill=opacity)
    layer=Image.new('RGBA',size,(*color,255))
    layer.putalpha(mask.filter(ImageFilter.GaussianBlur(12)))
    image.alpha_composite(layer,(x-padding,y-padding))


@lru_cache(maxsize=2)
def _background(scene):
    # At most two decoded member-free backgrounds, copied before live text.
    with Image.open(ASSETS/f'{scene}.jpg') as source:
        image=source.convert('RGBA')
        if image.size!=SIZE:image=image.resize(SIZE,Image.Resampling.LANCZOS)
    _veil(image,(284,215,803,558),(247,237,221),95)
    _veil(image,(197,594,650,706),(22,33,46),155)
    _veil(image,(832,594,1245,706),(22,33,46),155)
    _veil(image,(193,750,1060,830),(247,237,221),215)
    return image


def _line(draw,box,text,size,color,minimum=20,serif=True):
    x,y,w,h=box
    value=' '.join(str(text).split())[:180]
    family=_serif if serif and all(ord(c)<0x3000 for c in value) else font
    while size>minimum and draw.textlength(value,font=family(size))>w:size-=1
    face=family(size)
    if draw.textlength(value,font=face)>w:
        while value and draw.textlength(value+'…',font=face)>w:value=value[:-1]
        value+='…'
    bounds=draw.textbbox((0,0),value,font=face)
    draw.text((x-bounds[0],y+(h-(bounds[3]-bounds[1]))/2-bounds[1]),value,font=face,fill=color)


def _spark(draw,x,y,r,color=GOLD):
    draw.polygon(((x,y-r),(x+3,y-3),(x+r,y),(x+3,y+3),(x,y+r),
                  (x-3,y+3),(x-r,y),(x-3,y-3)),fill=color)


@lru_cache(maxsize=1)
def _portrait_mask():
    mask=Image.new('L',(228,228))
    ImageDraw.Draw(mask).ellipse((0,0,227,227),fill=255)
    return mask.resize((76,76),Image.Resampling.LANCZOS)


def render_fate(result,name,avatar=b''):
    scene,footer=SCENES.get(result.title,SCENES['The Wanderer'])
    image=_background(scene).copy();draw=ImageDraw.Draw(image)
    fields=dict(result.fields)
    draw.text((47,28),f'FATE  /  {str(result.day)[:16]}',font=_serif(27),fill=PALE)
    _line(draw,(47,69,1000,45),str(name)[:100],40,PALE,serif=False,minimum=22)
    draw.line((1110,69,1274,69),fill='#ad916e',width=1);_spark(draw,1224,69,10,'#d9b891')
    art=_asset(avatar) if len(avatar)<=6*1024*1024 else None
    if art is not None:
        image.paste(ImageOps.fit(art,(76,76),Image.Resampling.LANCZOS),(1303,32),_portrait_mask())
    else:
        draw.ellipse((1303,32,1379,108),fill='#32404d',outline='#d9b891',width=1)
        draw.text((1341,70),str(name).strip()[:1].upper() or 'M',font=font(30),fill=PALE,anchor='mm')
    draw=ImageDraw.Draw(image)
    heading='Y O U R  F A T E'
    draw.text((296,180),heading,font=_serif(19),fill=INK)
    line_x=296+round(draw.textlength(heading,font=_serif(19)))+18
    draw.line((line_x,190,line_x+37,190),fill=GOLD,width=1);_spark(draw,line_x+62,190,12,INK)
    _line(draw,(290,222,510,84),result.title,92,INK,minimum=36)
    _line(draw,(296,317,560,26),'T H E  A R C H E T Y P E  W A L K I N G  B E S I D E  Y O U',20,INK,minimum=14)
    draw.line((296,373,527,373),fill=GOLD,width=1)
    draw.line((571,373,806,373),fill=GOLD,width=1);_spark(draw,550,373,12)
    draw.text((296,409),'W H A T  T H I S  F A T E  M E A N S',font=_serif(18),fill=INK)
    _text(draw,(296,440,510,124),fields.get('Meaning',''),31,INK,minimum=21)
    for x,key,heading in ((210,'Path','P A T H'),(846,'Strength','C O R E  S T R E N G T H')):
        draw.text((x,609),heading,font=_serif(18),fill=PALE)
        draw.line((x,635,x+25,635),fill='#d9b891',width=1)
        _line(draw,(x,649,435 if x==210 else 425,47),fields.get(key,''),40,PALE,minimum=24)
    draw.text((210,755),'T H E  C H A P T E R  A H E A D',font=_serif(17),fill=INK)
    draw.line((210,778,235,778),fill=GOLD,width=1)
    _line(draw,(210,789,840,39),fields.get('Possible chapter',''),30,INK,minimum=22)
    for x,key,heading,width in ((210,'Guidance','G U I D A N C E',467),(905,'Omen','O M E N',370)):
        draw.text((x,884),heading,font=_serif(18),fill=INK)
        _text(draw,(x,916,width,76),fields.get(key,''),27,INK,minimum=18)
    footer_font=font(17)
    width=draw.textlength(footer,font=footer_font)
    draw.text(((SIZE[0]-width)/2,1030),footer,font=footer_font,fill=GOLD)
    output=BytesIO();image.convert('RGB').save(output,format='PNG',compress_level=2)
    return output.getvalue()
