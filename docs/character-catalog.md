# Character summon roster

Meyaya keeps a curated roster of 100 verified AniList character IDs. PostgreSQL stores only
Meyaya gameplay configuration: provider ID, rarity, summon weight, class, traits, passive,
and enable/disable controls.

`/summon` selects a rarity first using these rates:

- 2-star Uncommon: 45%
- 3-star Rare: 30%
- 4-star Epic: 17%
- 5-star Legendary: 7%
- 6-star Mythic: 1%

It then selects an enabled character in that tier using its summon weight. Name, primary
series, and artwork URL are fetched from AniList for that one explicit ID. Display data stays
in memory for three hours and is never written to PostgreSQL or downloaded as artwork.

## Deployment

Run `alembic upgrade head`. On startup, Meyaya adds any missing bundled gameplay IDs without
contacting AniList. Normal summons are the only routine provider requests.

## Hidden owner controls

Use these in a DM with Meyaya:

```text
uwu catalogadmin status
uwu catalogadmin add <AniList ID>
uwu catalogadmin disable <roster ID> <reason>
uwu catalogadmin enable <roster ID> <reason>
uwu catalogadmin disableimage <roster ID> <reason>
uwu catalogadmin enableimage <roster ID> <reason>
uwu catalogadmin setrarity <roster ID> <2-6>
uwu catalogadmin settraits <roster ID> <class | trait one, trait two | passive>
uwu catalogadmin reload
uwu catalogadmin blockprovider x <reason>
uwu catalogadmin unblockprovider x <reason>
```

`add` performs one transient AniList lookup to verify the explicit ID. `reload` reloads the
bundled gameplay file and preserves disable and takedown state. Catalog actions remain audited.

Character data and artwork are supplied by AniList and belong to their respective owners.
