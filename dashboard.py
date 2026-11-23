"""Start only Meyaya's local owner dashboard: python dashboard.py."""
from typing import Any, cast

from bot.web.local import run

if __name__ == '__main__':
    cast(Any, run)()
