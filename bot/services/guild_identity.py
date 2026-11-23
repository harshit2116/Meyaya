"""Preserve identity without replacing known owner names with failed lookups."""
from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from sqlalchemy import select, case
from sqlalchemy.dialects.postgresql import insert
from bot.models.guild_identity import GuildIdentity, GuildEvent


async def remember_identity(
    factory: Any,
    info: Mapping[str, Any],
    *,
    membership: bool | None = None,
    joined_at: datetime | None = None,
) -> None:
    values: dict[str, Any] = {"guild_id": int(info['id']), "name": info['name']}
    for key in ('owner_id', 'owner_name', 'icon_url'):
        if info.get(key) is not None:
            values[key] = int(info[key]) if key == 'owner_id' else info[key]
    async with factory() as session:
        updates: dict[str, Any] = {k: v for k, v in values.items() if k != 'guild_id'}
        if values.get('owner_id') and not values.get('owner_name'):
            updates['owner_name'] = case(
                (GuildIdentity.owner_id == values['owner_id'], GuildIdentity.owner_name), else_=None)
        upsert = insert(GuildIdentity).values(**values).on_conflict_do_update(
            index_elements=[GuildIdentity.guild_id], set_=updates
        )
        if membership is None:
            await session.execute(upsert)
        else:
            row = await session.scalar(
                select(GuildIdentity)
                .from_statement(upsert.returning(GuildIdentity))
                .execution_options(populate_existing=True)
            )
            if row is not None and row.is_current != membership:
                when = datetime.now(UTC)
                if membership:
                    row.joined_at = joined_at or when
                    kind = 'joined' if joined_at or row.is_current is False else 'first_observed'
                else:
                    row.left_at = when
                    kind = 'left'
                row.is_current = membership
                session.add(GuildEvent(guild_id=row.guild_id, event_type=kind,
                    occurred_at=(row.joined_at if membership else when),
                    details={'name': row.name, 'owner_id': str(row.owner_id) if row.owner_id else None, 'owner_name': row.owner_name, 'icon_url': row.icon_url}))
        await session.commit()


async def saved_identities(factory: Any) -> dict[int, dict[str, Any]]:
    async with factory() as session:
        rows = (await session.scalars(select(GuildIdentity))).all()
        return {row.guild_id: dict(id=str(row.guild_id), name=row.name,
                owner_id=str(row.owner_id) if row.owner_id else None,
                owner_name=row.owner_name, icon_url=row.icon_url,
                joined_at=row.joined_at.isoformat() if row.joined_at else None,
                left_at=row.left_at.isoformat() if row.left_at else None,
                last_activity_at=row.last_activity_at.isoformat() if row.last_activity_at else None) for row in rows}
