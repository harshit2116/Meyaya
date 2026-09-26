"""Offline import/render RSS probe. Run with python -m scripts.memory_smoke."""

import asyncio
import importlib
import pkgutil
import sys
from io import BytesIO
from types import SimpleNamespace

import bot.cogs
from PIL import Image
from bot.services.profile_aesthetic import ProfileAestheticService
from bot.services.profile_cards import aura_card, duostyle_card, profilecheck_card
from bot.utils.image_work import image_work


def peak_mb():
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
                (name, ctypes.c_size_t)
                for name in (
                    "peak",
                    "working",
                    "paged_peak",
                    "paged",
                    "nonpaged_peak",
                    "nonpaged",
                    "pagefile",
                    "pagefile_peak",
                )
            ]

        data = Counters()
        data.cb = ctypes.sizeof(data)
        kernel = ctypes.WinDLL("kernel32")
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        query = ctypes.WinDLL("psapi").GetProcessMemoryInfo
        query.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        if not query(kernel.GetCurrentProcess(), ctypes.byref(data), data.cb):
            raise ctypes.WinError()
        return data.peak / 1024**2
    import resource

    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (
        1024**2 if sys.platform == "darwin" else 1024
    )


async def main():
    for module in pkgutil.iter_modules(bot.cogs.__path__):
        importlib.import_module(f"bot.cogs.{module.name}")
    print(f"All cogs imported: peak RSS {peak_mb():.1f} MiB")
    output = BytesIO()
    Image.new("RGB", (512, 512), "#c870ab").save(output, "PNG")
    member = SimpleNamespace(
        id=1,
        display_name="Memory Test",
        avatar=True,
        guild_avatar=None,
        display_avatar=SimpleNamespace(is_animated=lambda: False),
    )
    visual = await image_work(
        ProfileAestheticService._analyze,
        member,
        avatar=output.getvalue(),
        banner=None,
        decoration=None,
        has_nameplate=False,
        has_server_tag=False,
        badge_count=0,
        accent_value=None,
        fingerprint="abcd1234",
    )
    for _ in range(10):
        await image_work(aura_card, visual)
        await image_work(profilecheck_card, visual)
        await image_work(duostyle_card, visual, visual)
    print(f"After 30 card renders: peak RSS {peak_mb():.1f} MiB")


if __name__ == "__main__":
    asyncio.run(main())
