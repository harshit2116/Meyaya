"""Small, deterministic evidence rules for profile advice. No AI or network calls.

Measurements describe pixels and simulated icon sizes, not faces, subjects or
artistic intent. OKLab uses the CSS Color 4 sRGB conversion matrices:
https://www.w3.org/TR/css-color-4/#color-conversion-code
"""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from math import atan2, degrees, hypot, sqrt
from PIL import Image, ImageChops, ImageDraw, ImageOps, ImageStat


@dataclass(frozen=True, slots=True)
class Advice:
    rule_id: str
    metric: str
    impact: float
    confidence: float
    fixability: float
    evidence: tuple[tuple[str, float], ...]
    title: str
    action: str
    reason: str

    @property
    def priority(self):
        return self.impact * self.confidence * self.fixability


@dataclass(frozen=True, slots=True)
class Critique:
    findings: tuple[Advice, ...]
    fallback: str
    measured: bool = True


@dataclass(frozen=True, slots=True)
class Features:
    palette: tuple
    contrast: float
    edge: float
    entropy: float
    lightness: float
    chroma: float


def oklab(rgb):
    """sRGB bytes to perceptually useful OKLab (L nominally 0..1)."""
    r,g,b = (v/255 for v in rgb)
    r,g,b = (v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in (r,g,b))
    l = (.4122214708*r + .5363325363*g + .0514459929*b)**(1/3)
    m = (.2119034982*r + .6806995451*g + .1073969566*b)**(1/3)
    s = (.0883024619*r + .2817188376*g + .6299787005*b)**(1/3)
    return (.2104542553*l+.793617785*m-.0040720468*s,
            1.9779984951*l-2.428592205*m+.4505937099*s,
            .0259040371*l+.7827717662*m-.808675766*s)


def _open(data):
    if not data:
        return None
    try:
        with Image.open(BytesIO(data)) as source:
            if source.width*source.height > 4_000_000:
                return None
            source.thumbnail((128,128),Image.Resampling.LANCZOS)
            return source.convert('RGBA')
    except (OSError, ValueError, Image.DecompressionBombError):
        return None


def _gray(image):
    background=Image.new('RGBA',image.size,(18,15,25,255))
    return Image.alpha_composite(background,image).convert('L')


def _edges(gray):
    if min(gray.size)<2:
        return 0.0
    horizontal=ImageChops.difference(gray.crop((1,0,gray.width,gray.height)),gray.crop((0,0,gray.width-1,gray.height)))
    vertical=ImageChops.difference(gray.crop((0,1,gray.width,gray.height)),gray.crop((0,0,gray.width,gray.height-1)))
    return (ImageStat.Stat(horizontal).mean[0]+ImageStat.Stat(vertical).mean[0])/2


def _features(image):
    small=image.copy()
    small.thumbnail((64,64),Image.Resampling.LANCZOS)
    raw=small.tobytes()
    pixels=[(r,g,b) for r,g,b,a in zip(raw[::4],raw[1::4],raw[2::4],raw[3::4]) if a>=128]
    if not pixels:
        return None
    strip=Image.new('RGB',(len(pixels),1))
    strip.putdata(pixels)
    quantized=strip.quantize(colors=6,method=Image.Quantize.MEDIANCUT).convert('RGB')
    counts=sorted(quantized.getcolors(len(pixels)) or [],reverse=True)
    # No synthetic display-palette padding or invisible decoration pixels.
    colors=tuple((count/len(pixels),oklab(color)) for count,color in counts if count/len(pixels)>=.03)
    total=sum(weight for weight,_ in colors)
    colors=tuple((weight/total,color) for weight,color in colors)
    gray=_gray(image)
    return Features(colors,ImageStat.Stat(gray).stddev[0],_edges(gray),gray.entropy(),
                    sum(w*c[0] for w,c in colors),
                    sum(w*hypot(c[1],c[2]) for w,c in colors))


def palette_relationship(left, right):
    """Frequency-weighted compatibility, including neutral and opposing hues.

    These are heuristic relationships, never a claim that a style is wrong.
    A compatible secondary accent can connect two different dominant colours.
    """
    def compare(source,target):
        score=shared=0.0
        for weight,a in source:
            best=0.0
            nearest=10.0
            for _,b in target:
                distance=sqrt(sum((x-y)**2 for x,y in zip(a,b)))
                nearest=min(nearest,distance)
                ca,cb=hypot(a[1],a[2]),hypot(b[1],b[2])
                if min(ca,cb)<.035:
                    relation=.86  # Neutral support is not a hue mismatch.
                else:
                    gap=abs((degrees(atan2(a[2],a[1])-atan2(b[2],b[1]))+180)%360-180)
                    relation=max(max(0,1-gap/85), .86 if gap>=145 else .72 if 100<=gap<=140 else .42)
                candidate=relation if min(ca,cb)<.035 else max(0,relation-max(0,abs(ca-cb)-(.15 if gap>=100 else .06))*1.6)
                best=max(best,candidate)
            score+=weight*best
            shared+=weight*(nearest<.10)
        total=sum(w for w,_ in source)
        return score/total,shared/total
    a,sa=compare(left.palette,right.palette)
    b,sb=compare(right.palette,left.palette)
    return (a+b)/2,(sa+sb)/2


def _icon_evidence(image):
    gray=ImageOps.fit(_gray(image),(128,128),method=Image.Resampling.LANCZOS)
    mask=Image.new('L',(128,128))
    ImageDraw.Draw(mask).ellipse((0,0,127,127),fill=255)
    base=max(1,ImageStat.Stat(gray,mask).stddev[0])
    samples=[]
    for size in (128,64,48,32,24):
        tiny=gray.resize((size,size),Image.Resampling.LANCZOS)
        tiny_mask=mask.resize((size,size),Image.Resampling.NEAREST)
        retained=min(1,ImageStat.Stat(tiny,tiny_mask).stddev[0]/base)
        restored=tiny.resize((128,128),Image.Resampling.BICUBIC)
        loss=min(1,ImageStat.Stat(ImageChops.difference(gray,restored),mask).rms[0]/base)
        samples.append((size,retained,loss))
    # FIND_EDGES excludes the artificial outside image boundary from the count.
    from PIL import ImageFilter
    edges=gray.filter(ImageFilter.FIND_EDGES)
    edges=edges.crop((2,2,126,126))
    circle=mask.crop((2,2,126,126))
    inside=ImageStat.Stat(edges,circle).sum[0]
    outside=ImageStat.Stat(edges,ImageOps.invert(circle)).sum[0]
    rim_share=outside/max(1,inside+outside)
    return dict((str(size),(retained,loss)) for size,retained,loss in samples),rim_share


def analyze_advice(visual):
    avatar=_open(visual.avatar)
    if avatar is None:
        return Critique((),"Your avatar could not be analysed. Try again once the image loads.", False)
    a=_features(avatar)
    if a is None:
        return Critique((),"The avatar has no sufficiently opaque pixels to review reliably.", False)
    samples,rim_share=_icon_evidence(avatar)
    retained,loss=samples['32']
    findings=[]
    def add(rule,metric,impact,confidence,fixability,evidence,title,action,reason):
        findings.append(Advice(rule,metric,impact,confidence,fixability,
            tuple((key,round(value,4)) for key,value in evidence.items()),title,action,reason))
    if a.edge>28 and loss>.55:
        add('avatar_fine_noise','readability',.88,.94,.85,
            dict(edge_energy=a.edge,loss_32=loss),
            'Fine texture gets lost at chat size.',
            'Keep the overall style, but try less fine texture and compare the avatar at 32 pixels.',
            'Much of the high-frequency detail disappears when reduced.')
    elif loss>.43 and retained<.82 and a.edge>9:
        add('avatar_small_detail_loss','readability',.78,.87,.85,
            dict(contrast_retained_32=retained,loss_32=loss),
            'Small details fade when the avatar is reduced.',
            'Test a slightly tighter crop or simplify tiny details, then compare at 24 and 32 pixels.',
            'The small version loses both contrast and fine detail.')
    if a.contrast<14:
        add('avatar_low_separation','readability',.8,.9,.8,
            dict(grayscale_contrast=a.contrast),
            'The avatar has little light-dark separation.',
            'Try a modest contrast increase around important shapes, keeping your current colours.',
            'Its measured grayscale contrast is low, which can hide shapes at chat size.')
    if rim_share>.43 and a.edge>4:
        add('avatar_circle_boundary','readability',.66,.82,.9,
            dict(edge_share_outside_circle=rim_share),
            'High-contrast detail falls outside the circular crop.',
            'Check the circular preview and move any important edge details inward before cropping.',
            'A large share of visible edges sits in the corners Discord crops away.')
    decoration=_open(visual.decoration)
    if decoration is not None:
        # Approximate the decoration's larger footprint around a circular avatar.
        overlay=Image.new('RGBA',(128,128))
        art=ImageOps.contain(decoration,(146,146),Image.Resampling.LANCZOS)
        overlay.alpha_composite(art,((128-art.width)//2,(128-art.height)//2))
        alpha=overlay.getchannel('A').crop((32,32,96,96))
        covered=sum(alpha.histogram()[160:])/4096
        if covered>.24:
            add('decoration_center_coverage','detail_balance',.9,.93,.8,
                dict(central_opaque_fraction=covered),
                'The decoration covers much of the avatar centre.',
                'Try a frame with a more open centre, or compare this avatar with the decoration off.',
                'In the overlay simulation, opaque decoration pixels cover the central area.')
    candidates=[]
    for name,data in (('banner',visual.banner),('nameplate',getattr(visual,'nameplate',None))):
        image=_open(data)
        if image is not None:
            candidates.append((name,image))
    if not visual.banner and not visual.banner_available and visual.accent_color:
        candidates.append(('profile colour',Image.new('RGBA',(64,64),visual.accent_color)))
    for name,image in candidates:
        other=_features(image)
        if other is None:
            continue
        compatibility,shared=palette_relationship(a,other)
        chroma_gap=abs(a.chroma-other.chroma)
        light_gap=abs(a.lightness-other.lightness)
        if chroma_gap>.11 and shared<.35 and compatibility<.77:
            add(name.replace(' ','_')+'_chroma_gap','color_harmony',.68,.86,.85,
                dict(chroma_gap=chroma_gap,shared_palette_fraction=shared,compatibility=compatibility),
                f'The {name} and avatar use different colour intensity.',
                f'Try a more muted accent in the {name}, or add a small shared accent while keeping both images.',
                'Their frequency-weighted palettes differ strongly in chroma.')
        elif compatibility<.53 and shared<.18 and light_gap>.32:
            add(name.replace(' ','_')+'_palette_gap','cohesion',.62,.8,.82,
                dict(compatibility=compatibility,shared_palette_fraction=shared,lightness_gap=light_gap),
                f'The {name} and avatar have little palette connection.',
                f'Try one shared accent between the avatar and {name}; keep the contrast if it is intentional.',
                'Their palettes have little overlap and a large lightness difference.')
        if name=='banner' and other.edge>max(20,a.edge*2.6) and a.entropy<4.5:
            add('banner_texture_competition','detail_balance',.56,.83,.8,
                dict(avatar_edge_energy=a.edge,banner_edge_energy=other.edge),
                'The banner has much denser texture than the avatar.',
                'Try a calmer banner crop while keeping its colours, or keep the contrast if you prefer it.',
                'The banner contains substantially more rapid light-dark changes.')
    # Stable tie-breaking, with one recommendation per underlying measurement.
    ranked=sorted(findings,key=lambda issue:(-issue.priority,issue.rule_id))
    chosen=[]
    families=set()
    for issue in ranked:
        family='palette' if issue.rule_id.endswith(('_chroma_gap','_palette_gap')) else issue.rule_id
        if family not in families:
            chosen.append(issue);families.add(family)
        if len(chosen)==3:
            break
    fallback=('Large flat areas are not a problem by themselves. Keep them if the small icon reads clearly.'
              if a.entropy<3 and a.contrast>=14 else
              'Keep your current style and check the avatar at normal chat size before changing it. Different palettes can be intentional.')
    return Critique(tuple(chosen),fallback)
