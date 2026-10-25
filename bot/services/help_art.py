"""Small immutable illustrations for native Discord help pages."""
from functools import lru_cache
from io import BytesIO
from pathlib import Path
import discord

ROOT=Path(__file__).resolve().parents[1]/'assets'/'celestial'/'help'
ART_NAMES=('directory',)


@lru_cache(maxsize=1)
def art_bytes():
    # One compact static banner only. Never cache File instances or per-user content.
    return tuple((f'help-{name}.jpg',(ROOT/f'{name}.jpg').read_bytes()) for name in ART_NAMES)


def help_files():
    return [discord.File(BytesIO(data),filename=name) for name,data in art_bytes()]


def gallery(name):
    return discord.ui.MediaGallery(discord.MediaGalleryItem(
        f'attachment://help-{name}.jpg',description={
            'directory':"Meyaya's command directory, framed by soft pink cherry blossoms.",
        }[name]))
