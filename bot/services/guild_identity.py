"""Preserve identity without replacing known owner names with failed lookups."""
from datetime import UTC, datetime
from sqlalchemy import select, case
from sqlalchemy.dialects.postgresql import insert
from bot.models.guild_identity import GuildIdentity, GuildEvent


async def remember_identity(factory, info, *, membership=None, joined_at=None):
    values = {"guild_id": int(info['id']), "name": info['name']}
    for key in ('owner_id', 'owner_name', 'icon_url'):
        if info.get(key) is not None:
            values[key] = int(info[key]) if key == 'owner_id' else info[key]
    async with factory() as session:
        updates = {k: v for k, v in values.items() if k != 'guild_id'}
        if values.get('owner_id') and not values.get('owner_name'):
            updates['owner_name'] = case(
                (GuildIdentity.owner_id == values['owner_id'], GuildIdentity.owner_name), else_=None)
        await session.execute(insert(GuildIdentity).values(**values).on_conflict_do_update(
            index_elements=[GuildIdentity.guild_id], set_=updates))
        if membership is not None:
            row = await session.scalar(select(GuildIdentity).where(
                GuildIdentity.guild_id == values['guild_id']).with_for_update())
            if row.is_current != membership:
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


async def saved_identities(factory):
    async with factory() as session:
        rows = (await session.scalars(select(GuildIdentity))).all()
        return {row.guild_id: dict(id=str(row.guild_id), name=row.name,
                owner_id=str(row.owner_id) if row.owner_id else None,
                owner_name=row.owner_name, icon_url=row.icon_url,
                joined_at=row.joined_at.isoformat() if row.joined_at else None,
                left_at=row.left_at.isoformat() if row.left_at else None,
                last_activity_at=row.last_activity_at.isoformat() if row.last_activity_at else None) for row in rows}
