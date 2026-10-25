"""Reference-matched three-card tarot spread with cached local artwork."""
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from PIL import Image,ImageDraw,ImageOps
from bot.services.aura_archive import _asset,_serif,_text
from bot.services.card_renderer import font
from bot.services.celestial import definitions

SIZE=(1536,1024)
ASSETS=Path(__file__).resolve().parents[1]/'assets'/'celestial'/'tarot'
GOLD='#eac395'
INK='#faf0e7'
CARD_SIZE=(252,390)
CENTERS=(325,768,1212)


@lru_cache(maxsize=1)
def _frame():
    with Image.open(ASSETS/'spread-frame.png') as source:
        return source.convert('RGBA').resize(SIZE,Image.Resampling.LANCZOS)


@lru_cache(maxsize=8)
def _card_art(number):
    try:
        with Image.open(ASSETS/f'{number:02d}.jpg') as source:
            # A contained full card preserves its printed name and all artwork.
            source.thumbnail((768,1152),Image.Resampling.LANCZOS)
            art=ImageOps.contain(source.convert('RGB'),(240,378),Image.Resampling.LANCZOS)
        plate=Image.new('RGB',CARD_SIZE,'#e6d0ae')
        plate.paste(art,((CARD_SIZE[0]-art.width)//2,(CARD_SIZE[1]-art.height)//2))
        return plate
    except (OSError,ValueError):
        return None


@lru_cache(maxsize=2)
def _mask(size,radius):
    mask=Image.new('L',(size[0]*3,size[1]*3))
    d=ImageDraw.Draw(mask)
    if radius is None:
        d.ellipse((0,0,mask.width-1,mask.height-1),fill=255)
    else:
        d.rounded_rectangle((0,0,mask.width-1,mask.height-1),radius=radius*3,fill=255)
    return mask.resize(size,Image.Resampling.LANCZOS)


def _centered(draw,box,text,size,minimum=20,serif=True,color=INK):
    x,y,w,h=box
    value=' '.join(str(text).split())[:180]
    family=_serif if serif and all(ord(c)<0x3000 for c in value) else font
    while True:
        face=family(size)
        rows=[];row=''
        for word in value.split():
            candidate=(row+' '+word).strip()
            if row and draw.textlength(candidate,font=face)>w:
                rows.append(row);row=word
            else:row=candidate
        rows.append(row)
        if size<=minimum or (len(rows)*(size+7)<=h and all(draw.textlength(r,font=face)<=w for r in rows)):
            break
        size-=1
    rows=rows[:max(1,h//(size+7))]
    top=y+(h-len(rows)*(size+7))/2
    for row in rows:
        if draw.textlength(row,font=face)>w:
            while row and draw.textlength(row+'…',font=face)>w:row=row[:-1]
            row+='…'
        bounds=draw.textbbox((0,0),row,font=face)
        draw.text((x+(w-draw.textlength(row,font=face))/2,top-bounds[1]+3),row,font=face,fill=color)
        top+=size+7


def _single_line(draw, box, text, size, *, serif=True, color=INK, minimum=20):
    """Fit a single label and centre its actual glyph bounds, including descenders."""
    x,y,w,h=box
    value=' '.join(str(text).split())[:180]
    family=_serif if serif else font
    while size>minimum and draw.textlength(value,font=family(size))>w:
        size-=1
    face=family(size)
    if draw.textlength(value,font=face)>w:
        while value and draw.textlength(value+'…',font=face)>w:value=value[:-1]
        value+='…'
    bounds=draw.textbbox((0,0),value,font=face)
    draw.text((x+(w-(bounds[2]-bounds[0]))/2-bounds[0],
               y+(h-(bounds[3]-bounds[1]))/2-bounds[1]),value,font=face,fill=color)


def render_tarot(result,name,avatar=b''):
    image=_frame().copy();draw=ImageDraw.Draw(image)
    draw.text((54,46),f'TAROT  /  {str(result.day)[:16]}',font=font(23),fill=GOLD)
    _text(draw,(54,82,510,48),str(name)[:100],40,INK,minimum=22,serif=False)
    draw.rounded_rectangle((54,135,93,140),radius=2,fill=GOLD)
    # Circular member portrait stays native content, never baked into the frame.
    art=_asset(avatar) if len(avatar)<=6*1024*1024 else None
    if art is not None:
        image.paste(ImageOps.fit(art,(82,82),Image.Resampling.LANCZOS),(1400,55),_mask((82,82),None))
    else:
        draw.ellipse((1400,55,1482,137),fill='#32273f',outline=GOLD,width=1)
        draw.text((1441,96),str(name).strip()[:1].upper() or 'M',font=font(30),fill=INK,anchor='mm')
    draw=ImageDraw.Draw(image)
    _centered(draw,(237,160,1062,58),'THREE THREADS OF YOUR STORY',47,minimum=35,color=GOLD)
    # Fixed, separate slots keep every subtitle clear of both separator stars
    # and the decorative rules baked into the frame.
    for text,center in (('P A S T',594),('P R E S E N T',768),('F U T U R E',927)):
        _single_line(draw,(center-72,222,144,28),text,20,serif=False,color=GOLD)
    for cx in (660,852):
        draw.polygon(((cx,226),(cx+3,233),(cx+8,236),(cx+3,239),(cx,246),
                      (cx-3,239),(cx-8,236),(cx-3,233)),fill=GOLD)
    names=[card[0] for card in definitions()['tarot']]
    for center,(position,title,meaning) in zip(CENTERS,result.panels[:3]):
        _centered(draw,(center-150,309,300,37),str(position).upper(),23,serif=False,color=GOLD)
        try:number=names.index(title.removesuffix(' (R)'))
        except ValueError:number=-1
        card=_card_art(number) if number>=0 else None
        box=(center-CARD_SIZE[0]//2,355)
        if card is not None:
            # Transpose returns a new image; never rotate the shared cached card.
            if title.endswith(' (R)'):card=card.transpose(Image.Transpose.ROTATE_180)
            image.paste(card,box,_mask(CARD_SIZE,12))
        else:
            draw.rounded_rectangle((*box,box[0]+252,745),radius=12,fill='#32283f',outline=GOLD,width=1)
            _centered(draw,(box[0]+20,490,212,100),'Artwork unavailable',26)
        # Card titles have their own single-line band below the star ornament
        # and above the interpretation border; long titles shrink consistently.
        _single_line(draw,(center-174,772,348,32),title,31,minimum=22)
        _centered(draw,(center-161,825,322,74),meaning,28,minimum=21,color='#e9c6b1')
    draw.text((768,965),'M E Y A Y A   ·   A  L I T T L E  P E R S P E C T I V E  F O R  T O D A Y',
              font=font(16),fill=GOLD,anchor='mm')
    output=BytesIO();image.convert('RGB').save(output,format='PNG',compress_level=2)
    return output.getvalue()
