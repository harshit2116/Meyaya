"""Provider-independent gameplay roster for on-demand character summons."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
import json
from random import SystemRandom

from sqlalchemy import func, select

from bot.models.character_catalog import CatalogAudit, CatalogCharacter, CatalogProviderState

NOTICE = "Character data and artwork: AniList. Rights belong to their respective owners."
DRAW_RATES = {2: 45, 3: 30, 4: 17, 5: 7, 6: 1}
RARITY_NAMES = {2: "Uncommon", 3: "Rare", 4: "Epic", 5: "Legendary", 6: "Mythic"}
RNG = SystemRandom()


@dataclass(frozen=True, slots=True)
class GameplayDraw:
    internal_id: int
    provider: str
    provider_character_id: int
    rarity_stars: int
    class_name: str
    traits: tuple[str, ...]
    passive: str
    image_disabled: bool


def load_curated_roster() -> list[dict]:
    payload = json.loads(files("bot.data").joinpath("character_roster.json").read_text("utf-8"))
    entries = payload.get("characters", [])
    if len(entries) < 100:
        raise RuntimeError("The curated summon roster must contain at least 100 characters.")
    seen: set[int] = set()
    for item in entries:
        provider_id = int(item["anilist_id"])
        rarity = int(item["rarity_stars"])
        weight = int(item.get("summon_weight", 100))
        if provider_id in seen or rarity not in DRAW_RATES or weight < 1:
            raise RuntimeError("The curated summon roster contains invalid or duplicate entries.")
        seen.add(provider_id)
    return entries


class CatalogService:
    def __init__(self, bot):
        self.bot = bot

    async def seed_curated_roster(self) -> int:
        """Add missing bundled IDs without overwriting owner changes or safety flags."""
        roster = load_curated_roster()
        async with self.bot.session_factory() as db:
            existing = set(
                await db.scalars(
                    select(CatalogCharacter.provider_character_id).where(
                        CatalogCharacter.provider == "anilist"
                    )
                )
            )
            added = 0
            for item in roster:
                source_id = str(int(item["anilist_id"]))
                if source_id in existing:
                    continue
                db.add(self._row_from_item(item))
                added += 1
            if added:
                db.add(
                    CatalogAudit(
                        actor_id=0,
                        action="seed_roster",
                        target="anilist",
                        reason=f"Added {added} bundled gameplay IDs; no provider lookup performed",
                    )
                )
                await db.commit()
            return added

    async def reload_curated_roster(self, actor: int) -> int:
        """Reload Meyaya gameplay fields while preserving disable and takedown state."""
        roster = load_curated_roster()
        async with self.bot.session_factory() as db:
            rows = {
                row.provider_character_id: row
                for row in await db.scalars(
                    select(CatalogCharacter).where(CatalogCharacter.provider == "anilist")
                )
            }
            for item in roster:
                source_id = str(int(item["anilist_id"]))
                row = rows.get(source_id)
                if row is None:
                    db.add(self._row_from_item(item))
                    continue
                row.rarity_stars = int(item["rarity_stars"])
                row.summon_weight = int(item.get("summon_weight", 100))
                row.class_name = str(item.get("class", "Wanderer"))[:80]
                row.traits = [str(value)[:60] for value in item.get("traits", [])[:4]]
                row.passive = str(item.get("passive", ""))[:250]
            db.add(
                CatalogAudit(
                    actor_id=actor,
                    action="reload_roster",
                    target="anilist",
                    reason=f"Reloaded {len(roster)} bundled gameplay entries",
                )
            )
            await db.commit()
            return len(roster)

    async def draw(self) -> GameplayDraw | None:
        async with self.bot.session_factory() as db:
            provider = await db.get(CatalogProviderState, "anilist")
            if provider and provider.blocked:
                return None
            available = set(
                await db.scalars(
                    select(CatalogCharacter.rarity_stars)
                    .where(
                        CatalogCharacter.provider == "anilist",
                        CatalogCharacter.enabled.is_(True),
                        CatalogCharacter.disabled.is_(False),
                    )
                    .distinct()
                )
            )
            tiers = [tier for tier in DRAW_RATES if tier in available]
            if not tiers:
                return None
            rarity = RNG.choices(tiers, weights=[DRAW_RATES[tier] for tier in tiers], k=1)[0]
            rows = list(
                await db.scalars(
                    select(CatalogCharacter).where(
                        CatalogCharacter.provider == "anilist",
                        CatalogCharacter.rarity_stars == rarity,
                        CatalogCharacter.enabled.is_(True),
                        CatalogCharacter.disabled.is_(False),
                    )
                )
            )
            row = RNG.choices(rows, weights=[entry.summon_weight for entry in rows], k=1)[0]
            return GameplayDraw(
                internal_id=row.id,
                provider=row.provider,
                provider_character_id=int(row.provider_character_id),
                rarity_stars=row.rarity_stars,
                class_name=row.class_name,
                traits=tuple(row.traits or []),
                passive=row.passive,
                image_disabled=row.image_disabled,
            )

    async def add_character(self, provider_id: int, actor: int) -> int:
        async with self.bot.session_factory() as db:
            row = await db.scalar(
                select(CatalogCharacter).where(
                    CatalogCharacter.provider == "anilist",
                    CatalogCharacter.provider_character_id == str(int(provider_id)),
                )
            )
            if row:
                row.enabled = True
                row.disabled = False
            else:
                row = CatalogCharacter(
                    provider="anilist",
                    provider_character_id=str(int(provider_id)),
                    rarity_stars=3,
                    summon_weight=100,
                    class_name="Wanderer",
                    traits=["Uncharted"],
                    passive="A newly discovered presence.",
                    enabled=True,
                    disabled=False,
                    image_disabled=False,
                )
                db.add(row)
                await db.flush()
            db.add(
                CatalogAudit(
                    actor_id=actor,
                    action="add",
                    target=str(row.id),
                    reason=f"Added explicit AniList ID {int(provider_id)}",
                )
            )
            await db.commit()
            return row.id

    async def manage(self, action: str, target: str, value: str, actor: int) -> None:
        async with self.bot.session_factory() as db:
            if action in {"blockprovider", "unblockprovider"}:
                state = await db.get(CatalogProviderState, "anilist")
                if state is None:
                    state = CatalogProviderState(provider="anilist", blocked=False)
                    db.add(state)
                state.blocked = action == "blockprovider"
                state.reason = value[:500]
                audit_target = "anilist"
            else:
                row = await db.get(CatalogCharacter, int(target))
                if row is None:
                    raise ValueError("Unknown internal summon character ID.")
                audit_target = str(row.id)
                if action in {"disable", "remove"}:
                    row.disabled = True
                    row.takedown_reason = value[:500] or "Owner disabled"
                elif action == "enable":
                    row.disabled = False
                    row.enabled = True
                    row.takedown_reason = None
                elif action == "disableimage":
                    row.image_disabled = True
                    row.takedown_reason = value[:500] or "Image disabled"
                elif action == "enableimage":
                    row.image_disabled = False
                elif action == "setrarity":
                    rarity = int(value)
                    if rarity not in DRAW_RATES:
                        raise ValueError("Rarity must be from 2 through 6 stars.")
                    row.rarity_stars = rarity
                elif action == "settraits":
                    parts = [part.strip() for part in value.split("|")]
                    if len(parts) != 3:
                        raise ValueError("Use: class | trait one, trait two | passive")
                    row.class_name = parts[0][:80]
                    row.traits = [
                        trait.strip()[:60] for trait in parts[1].split(",") if trait.strip()
                    ][:4]
                    row.passive = parts[2][:250]
                else:
                    raise ValueError("Unknown catalog action.")
            db.add(
                CatalogAudit(
                    actor_id=actor,
                    action=action,
                    target=audit_target,
                    reason=value[:500] or action,
                )
            )
            await db.commit()

    async def status(self) -> dict:
        async with self.bot.session_factory() as db:
            total = await db.scalar(select(func.count()).select_from(CatalogCharacter))
            enabled = await db.scalar(
                select(func.count())
                .select_from(CatalogCharacter)
                .where(CatalogCharacter.enabled.is_(True), CatalogCharacter.disabled.is_(False))
            )
            blocked = await db.get(CatalogProviderState, "anilist")
            return {
                "total": total or 0,
                "enabled": enabled or 0,
                "blocked": bool(blocked and blocked.blocked),
            }

    @staticmethod
    def _row_from_item(item: dict) -> CatalogCharacter:
        return CatalogCharacter(
            provider="anilist",
            provider_character_id=str(int(item["anilist_id"])),
            rarity_stars=int(item["rarity_stars"]),
            summon_weight=int(item.get("summon_weight", 100)),
            class_name=str(item.get("class", "Wanderer"))[:80],
            traits=[str(value)[:60] for value in item.get("traits", [])[:4]],
            passive=str(item.get("passive", ""))[:250],
            enabled=True,
            disabled=False,
            image_disabled=False,
        )
