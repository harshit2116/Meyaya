"""Local editorial daily-fortune card; no generated art or additional API calls."""
from datetime import date
from functools import lru_cache
from io import BytesIO
import math

from PIL import Image, ImageDraw, ImageOps
from bot.services.aura_archive import _serif, _text
from bot.services.card_renderer import font

SIZE = (1400, 1120)
GOLD = '#efd096'
INK = '#faf4ee'
MUTED = '#d6c9e3'
HERO = (48, 220, 1360, 568)
METER_SIZE = 292
METER_POSITION = (1056, 262)
LUCK_COLORS = {'rose gold':'#d896a1','lavender':'#b19ad6','sky blue':'#93c9e8',
               'mint':'#9bd7bf','gold':'#e9c675','silver':'#bec8d6','moonlit silver':'#c7c9dd','midnight blue':'#343d70','soft peach':'#efbda6','coral':'#ea9c91',
               'pearl':'#ece6df','violet':'#9e83c7','sage':'#a6bc99','blush':'#edb8c8',
               'crimson':'#c6546b','teal':'#65bdb8','amber':'#dfb56c','lilac':'#c1a6dc'}


def _spark(draw, x, y, radius, color=GOLD):
    draw.polygon([(x,y-radius),(x+radius*.27,y-radius*.27),(x+radius,y),
                  (x+radius*.27,y+radius*.27),(x,y+radius),(x-radius*.27,y+radius*.27),
                  (x-radius,y),(x-radius*.27,y-radius*.27)],fill=color)


@lru_cache(maxsize=8)
def _icon(kind):
    image=Image.new('RGBA',(288,288))
    d=ImageDraw.Draw(image)
    def ellipse(box,**kw): d.ellipse(tuple(round(v*3) for v in box),**kw)
    def line(points,width=2): d.line([(int(x*3),int(y*3)) for x,y in points],fill=GOLD,width=width*3,joint='curve')
    if kind=='moon':
        ellipse((9,10,77,78),fill=GOLD)
        ellipse((35,1,86,64),fill=(0,0,0,0))
        _spark(d,241,123,25);_spark(d,210,47,14)
    elif kind=='dice':
        d.polygon([(48*3,12*3),(80*3,30*3),(48*3,49*3),(16*3,30*3)],fill=GOLD)
        d.polygon([(16*3,34*3),(45*3,52*3),(45*3,85*3),(16*3,66*3)],fill=GOLD)
        d.polygon([(51*3,52*3),(80*3,34*3),(80*3,66*3),(51*3,85*3)],fill=GOLD)
        for x,y in ((48,30),(26,48),(35,67),(62,53),(70,49),(62,70)):
            ellipse((x-3,y-3,x+3,y+3),fill='#30253e')
    elif kind=='theme':
        for angle in range(4):
            a=angle*math.pi/2
            x,y=144+math.sin(a)*53,144+math.cos(a)*53
            d.ellipse((x-23,y-38,x+23,y+38),fill=GOLD) if angle%2==0 else d.ellipse((x-38,y-23,x+38,y+23),fill=GOLD)
        d.ellipse((127,127,161,161),fill='#30253e')
    elif kind=='omen':
        points=[]
        for i in range(16):
            a=i*math.pi/8
            radius=(113 if i%4==0 else 77) if i%2==0 else 23
            points.append((144+math.cos(a)*radius,144+math.sin(a)*radius))
        d.polygon(points,fill=GOLD)
    elif kind=='compass':
        ellipse((9,9,87,87),outline=GOLD,width=15)
        d.polygon([(62*3,27*3),(54*3,55*3),(27*3,68*3),(39*3,40*3)],fill=GOLD)
        ellipse((44,44,52,52),fill='#30253e')
        for x,y in ((48,18),(48,78),(18,48),(78,48)):
            ellipse((x-2,y-2,x+2,y+2),fill=GOLD)
    return image.resize((72,72),Image.Resampling.LANCZOS)


def _panel(draw, box):
    draw.rounded_rectangle(box,radius=18,fill='#272138',outline='#605073',width=2)


def _flowers(image, box, mirror=False):
    """Clipped, reusable-in-the-base floral silhouettes kept away from copy."""
    w,h=box[2]-box[0],box[3]-box[1]
    layer=Image.new('RGBA',(w,h));d=ImageDraw.Draw(layer)
    color=(147,110,163,45)
    d.line([(w-4,h),(w-46,h-38),(w-28,h-87),(w-65,h-137)],fill=color,width=3)
    for cx,cy,r in ((w-29,h-22,23),(w-72,h-67,16),(w-25,h-115,19)):
        for j in range(5):
            angle=j*math.tau/5
            px,py=cx+math.sin(angle)*r*.78,cy+math.cos(angle)*r*.78
            size=r*.47
            d.ellipse((px-size,py-size,px+size,py+size),fill=color)
        d.ellipse((cx-3,cy-3,cx+3,cy+3),fill=(174,143,185,50))
    for x,y in ((w-83,h-102),(w-49,h-157),(w-110,h-47)):
        d.polygon([(x,y),(x-18,y-8),(x-22,y-24),(x-8,y-18)],fill=color)
    if mirror:layer=ImageOps.mirror(layer)
    mask=Image.new('L',(w,h));ImageDraw.Draw(mask).rounded_rectangle((0,0,w-1,h-1),radius=18,fill=255)
    layer.putalpha(Image.composite(layer.getchannel('A'),Image.new('L',(w,h)),mask))
    image.alpha_composite(layer,(box[0],box[1]))


@lru_cache(maxsize=1)
def _base():
    # One member-free static layer. Copy before drawing dates, names or portraits.
    gradient=Image.new('RGB',(1,280))
    gradient.putdata([(19+int(5*math.sin(y/280*math.pi)),17+int(3*math.sin(y/280*math.pi)),
                       32+int(7*math.sin(y/280*math.pi))) for y in range(280)])
    image=gradient.resize(SIZE).convert('RGBA');d=ImageDraw.Draw(image)
    d.rounded_rectangle((20,20,1380,1100),radius=26,outline=GOLD,width=2)
    image.alpha_composite(_icon('moon'),(42,31))
    d.text((150,54),'D A I L Y  F O R T U N E',font=font(26),fill=GOLD)
    d.line((460,69,697,69),fill=GOLD,width=1);d.line((734,69,1102,69),fill=GOLD,width=1)
    _spark(d,715,69,11)
    d.line((82,199,124,199),fill=GOLD,width=4)
    d.rounded_rectangle(HERO,radius=22,fill='#30283f',outline='#8d739f',width=2)
    boxes=((48,598,467,750),(492,598,913,750),(938,598,1360,750),
           (48,774,694,986),(720,774,1360,986))
    for index,box in enumerate(boxes):
        _panel(d,box);_flowers(image,box,mirror=index==3)
    for kind,pos in (('dice',(70,616)),('theme',(960,615)),('omen',(72,792)),('compass',(746,792))):
        image.alpha_composite(_icon(kind),pos)
    return image


@lru_cache(maxsize=1)
def _hero_mask():
    width,height=HERO[2]-HERO[0],HERO[3]-HERO[1]
    mask=Image.new('L',(width,height));d=ImageDraw.Draw(mask)
    d.rounded_rectangle((0,0,width-1,height-1),radius=22,fill=255)
    fade=Image.new('L',(width,1))
    fade.putdata([round(235*max(0,min(1,(x-552)/430))) for x in range(width)])
    from PIL import ImageChops
    return ImageChops.multiply(mask,fade.resize((width,height)))


def _avatar(image, data):
    if not data or len(data)>6*1024*1024:return
    try:
        with Image.open(BytesIO(data)) as source:
            if source.width*source.height>4_000_000:return
            source.thumbnail((1024,1024))
            art=ImageOps.fit(source.convert('RGBA'),(700,348),centering=(.5,.36))
        layer=Image.new('RGBA',(1312,348),'#30283f')
        layer.alpha_composite(art,(552,0))
        # A translucent violet tint integrates the real avatar without replacing it.
        layer=Image.blend(layer,Image.new('RGBA',layer.size,'#53405e'),.14)
        image.paste(layer,HERO[:2],_hero_mask())
        ImageDraw.Draw(image).rounded_rectangle(HERO,radius=22,outline='#8d739f',width=2)
    except (OSError,ValueError):pass


def _meter(luck):
    # Every ellipse uses the same square coordinates. Supersampling preserves
    # round edges; no independent horizontal or vertical scaling is applied.
    scale=3;size=METER_SIZE
    art=Image.new('RGBA',(size*scale,size*scale));d=ImageDraw.Draw(art)
    d.ellipse((0,0,size*scale-1,size*scale-1),fill='#211b31',outline='#483952',width=6)
    bounds=(16*scale,16*scale,(size-17)*scale,(size-17)*scale)
    d.ellipse(bounds,outline='#51465e',width=10*scale)
    if luck:
        d.arc(bounds,start=-90,end=-90+luck*3.6,fill=GOLD,width=10*scale)
    return art.resize((size,size),Image.Resampling.LANCZOS)


def render_fortune(result, name, avatar=b''):
    fields=dict(result.fields)
    image=_base().copy();_avatar(image,avatar)
    oracle=fields.get('Question oracle')
    if oracle:
        expanded=Image.new('RGBA',(1400,1260),'#141120');expanded.paste(image.crop((0,0,1400,1010)),(0,0));image=expanded
    d=ImageDraw.Draw(image)
    try:day=date.fromisoformat(result.day).strftime('%d %b %Y').upper()
    except (ValueError,TypeError):day=str(result.day)[:16]
    d.text((1350,54),day,font=font(26),fill=GOLD,anchor='ra')
    _text(d,(80,98,1240,94),str(name)[:100],80,INK,minimum=26)
    heading='T O D A Y ’ S  C H A P T E R'
    d.text((98,264),heading,font=font(23),fill=GOLD)
    line_x=98+round(d.textlength(heading,font=font(23)))+24
    d.line((line_x,278,line_x+66,278),fill=GOLD,width=2)
    _text(d,(94,327,930,86),result.title,64,INK,minimum=29)
    _text(d,(98,422,770,124),fields.get('Outlook',''),34,MUTED,minimum=24)
    luck=max(0,min(100,int(fields.get('Luck','0/100').split('/')[0])))
    image.alpha_composite(_meter(luck),METER_POSITION);d=ImageDraw.Draw(image)
    cx,cy=METER_POSITION[0]+METER_SIZE/2,METER_POSITION[1]+METER_SIZE/2
    d.text((cx,cy-14),str(luck),font=_serif(100),fill=INK,anchor='mm')
    d.text((cx,cy+48),'L U C K  /  1 0 0',font=font(19),fill=GOLD,anchor='mm')
    _spark(d,cx,cy+83,11)
    for x,key,value in ((176,'L U C K Y  N U M B E R',fields.get('Lucky number','')),
                         (632,'C O L O R',fields.get('Color','')),
                         (1054,'T H E M E',fields.get('Lucky theme',''))):
        d.text((x,624),key,font=font(19),fill=GOLD)
        d.line((x,662,x+23,662),fill=GOLD,width=3)
        _text(d,(x,676,275 if x<1000 else 280,64),value,56 if x==176 else 38,INK,minimum=22)
    color=LUCK_COLORS.get(fields.get('Color','').casefold(),'#c3a9d5')
    d.ellipse((526,626,594,694),fill=color,outline=GOLD,width=3)
    d.pieslice((531,631,589,689),start=180,end=270,fill='#f6ded4')
    for x,key,heading in ((184,'Omen','O M E N'),(860,'Advice','T O D A Y ’ S  G U I D A N C E')):
        d.text((x,805),heading,font=font(20),fill=GOLD)
        d.line((x,842,x+23,842),fill=GOLD,width=3)
        _text(d,(x,865,460,101),fields.get(key,''),35,INK,minimum=24)
    if oracle:
        _panel(d,(48,1010,1360,1134))
        d.text((82,1031),'Y O U R  Q U E S T I O N  ·  T H E  O R A C L E',font=font(20),fill=GOLD)
        _text(d,(82,1072,1250,49),oracle,30,INK,minimum=23)
        d.rounded_rectangle((20,20,1380,1240),radius=26,outline=GOLD,width=2)
    footer=1187 if oracle else 1048
    d.line((102,footer,390,footer),fill=GOLD,width=1);d.line((1014,footer,1304,footer),fill=GOLD,width=1)
    _spark(d,82,footer,11);_spark(d,1323,footer,11)
    d.text((700,footer),'M E Y A Y A  ·  A  L I T T L E  P E R S P E C T I V E  F O R  T O D A Y',font=font(17),fill=GOLD,anchor='mm')
    output=BytesIO();image.convert('RGB').save(output,format='PNG',compress_level=2)
    return output.getvalue()
