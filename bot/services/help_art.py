"""Small immutable illustrations for native Discord help pages."""
from functools import lru_cache
from io import BytesIO
from pathlib import Path
import discord

ROOT=Path(__file__).resolve().parents[1]/'assets'/'celestial'/'help'
ART_NAMES=('garden','discover','connect')


@lru_cache(maxsize=1)
def art_bytes():
    # Three static JPEGs only. Never cache File instances or per-user content.
    return tuple((f'help-{name}.jpg',(ROOT/f'{name}.jpg').read_bytes()) for name in ART_NAMES)


def help_files():
    return [discord.File(BytesIO(data),filename=name) for name,data in art_bytes()]


def gallery(name):
    return discord.ui.MediaGallery(discord.MediaGalleryItem(
        f'attachment://help-{name}.jpg',description={
            'garden':"Meyaya welcoming you to her moonlit Command Garden.",
            'discover':"A celestial gateway to profile styles, fortunes and adventures.",
            'connect':"A lantern-lit garden for friendships, conversations and playful chaos.",
        }[name]))
