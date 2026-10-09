"""Application-owned, transactional campaign state machine. No background work."""

from datetime import UTC, datetime
from hashlib import sha256
import secrets
from uuid import uuid4
from sqlalchemy.exc import DBAPIError

from bot.data.fantasy_dungeon import world_for
from bot.data.fantasy_memory_world import OPENING, CORE, STORY_VERSION, CYCLE, ending_scenes
from bot.data.fantasy_dungeon_lore import lore_scenes
from bot.models.fantasy_dungeon import FantasyDungeonRun, ACTIVE_PHASES
from bot.repositories.fantasy_dungeon import FantasyDungeonRepository
from bot.repositories.fantasy_profiles import FantasyProfileRepository
from bot.repositories.fantasy_duels import FantasyDuelRepository
from bot.services.fantasy_duel import Fighter, RULES_VERSION
from bot.services.fantasy_dungeon_combat import DungeonCombat, enemy_fighter
from bot.services.fantasy_progression import award_xp
from bot.data.private_identity import AYAYA_USER_ID


class DungeonUnavailable(ValueError):
    pass


class DungeonStale(DungeonUnavailable):
    pass


class DungeonService:
    def __init__(self, session):
        self.session = session
        self.profiles = FantasyProfileRepository(session)
        self.runs = FantasyDungeonRepository(session)

    async def read(self, user_id):
        for attempt in range(2):
            try:
                return await self.runs.soul(user_id)
            except DBAPIError as error:
                if attempt or not error.connection_invalidated:
                    raise
                await self.session.rollback()

    async def owner_control(self, user_id, action, *, guild_id):
        if user_id != AYAYA_USER_ID:
            raise DungeonUnavailable("These dungeon controls are owner-only.")
        if action not in {"restart", "skip"}:
            raise DungeonUnavailable("Use `uwu dungeon restart` or `uwu dungeon skip`.")
        async with self.session.begin():
            profile = await self.profiles.locked(user_id)
            if profile is None or profile.alignment not in {"meyaya", "veyra"}:
                raise DungeonUnavailable("Awaken and choose your patron before using dungeon controls.")
            run = await self.runs.get(user_id, lock=True)
            if action == "restart":
                if profile.ending_route:
                    raise DungeonUnavailable("Your worldline is permanent. Restart cannot erase a final choice.")
                if run is None:
                    run = FantasyDungeonRun(user_id=user_id)
                    self.session.add(run)
                profile.weapon_level, profile.highest_floor = 0, 1
                run.token, run.seed = uuid4().hex, secrets.randbits(62)
                run.floor, run.encounter, run.revision = 1, 0, 0
                run.phase, run.hp, run.mp = "intro", profile.max_hp, profile.max_mp
                run.state = dict(guild_id=guild_id, scene=0, sequence="opening", story_version=STORY_VERSION)
            else:
                if run is None or run.phase != "combat" or run.floor == 10:
                    raise DungeonUnavailable("There is no current battle to skip.")
                combat = DungeonCombat.restore(run.state["battle"], run.seed + run.floor * 100 + run.encounter,
                                               run.floor, run.encounter)
                state = combat.state
                state.right.hp, state.finished, state.winner_id = 0, True, user_id
                state.log = ["Battle skipped by the owner."]
                await self.reward_victory(profile, run, state, run.state["guild_id"], owner_skip=True)
                run.revision += 1
            run.updated_at = datetime.now(UTC)
            await self.session.flush()
            return profile, run

    async def transition(self, user_id, action, *, token=None, revision=None, guild_id=0):
        for attempt in range(2):
            try:
                return await self._transition_once(user_id, action, token=token, revision=revision, guild_id=guild_id)
            except DBAPIError as error:
                if attempt or not error.connection_invalidated:
                    raise
                # A socket may drop just after its health check. Reconnect once
                # with the SAME captured token/revision. If the prior commit
                # reached Postgres, stale-action checks prevent a second turn
                # or reward; never retry with a freshly fetched revision.
                await self.session.rollback()

    async def _transition_once(self, user_id, action, *, token=None, revision=None, guild_id=0):
        async with self.session.begin():
            if action == "begin":
                # A concurrent Begin may insert the first run while waiting for
                # the profile lock. Its run lookup needs a fresh READ COMMITTED
                # statement snapshot, so keep the two-step admission path.
                profile = await self.profiles.locked(user_id)
                run = await self.runs.get(user_id, lock=True) if profile is not None else None
            else:
                profile, run = await self.runs.soul(user_id, lock=True)
            if profile is None:
                raise DungeonUnavailable("Use `/awaken` before beginning the descent.")
            if profile.alignment not in {"meyaya", "veyra"}:
                raise DungeonUnavailable("Choose your patron through `/fantasyprofile` before entering.")
            if action == "begin":
                # Start buttons are themselves versioned, including sanctuary
                # after a failure. An old Begin cannot restart an abandoned run.
                if (token is None and run is not None) or (
                    token is not None and (run is None or run.token != token or run.revision != revision)
                ):
                    raise DungeonStale("This entrance is stale. Open `/dungeon` again.")
                if run is not None and run.phase in ACTIVE_PHASES:
                    return profile, run
                if profile.ending_route:
                    raise DungeonUnavailable("The Tenfold Descent is complete. Your soul remembers the ending.")
                first_entry = run is None
                if run is None:
                    run = FantasyDungeonRun(user_id=user_id)
                    self.session.add(run)
                floor = min(10, profile.weapon_level + 1)
                run.token, run.seed = uuid4().hex, secrets.randbits(62)
                run.floor, run.encounter, run.revision = floor, 0, 0
                run.hp, run.mp = profile.max_hp, profile.max_mp
                run.phase = "seal" if floor == 10 else "intro"
                run.state = dict(guild_id=guild_id, scene=0, story_version=STORY_VERSION)
                if floor == 10:
                    run.state = dict(run.state, sequence="core")
                elif first_entry:
                    run.state = dict(run.state, sequence="opening")
                profile.highest_floor = max(profile.highest_floor, floor)
            else:
                if run is None or run.token != token or run.revision != revision:
                    raise DungeonStale("This button belongs to an earlier turn. Open `/dungeon` to resume.")
                if run.phase not in ACTIVE_PHASES:
                    raise DungeonStale("This run has ended. Open `/dungeon` again.")
                if action == "abandon":
                    if profile.ending_route:
                        raise DungeonUnavailable("Your worldline is sealed. Continue the ending with `/dungeon`.")
                    run.phase, run.hp, run.mp, run.state = "abandoned", 0, 0, {}
                elif action in {"choose_meyaya", "choose_veyra"}:
                    if run.phase != "seal" or run.state.get("sequence") != "choice" or profile.ending_route:
                        raise DungeonUnavailable("The final choice is not available here.")
                    profile.ending_route = action.removeprefix("choose_")
                    profile.ending_chosen_at = datetime.now(UTC)
                    run.state = dict(run.state, sequence="ending", scene=0)
                elif action == "continue":
                    self.advance(profile, run)
                elif run.phase == "combat" and action in {"attack", "ability", "guard"}:
                    await self.combat_turn(profile, run, action)
                else:
                    raise DungeonUnavailable("That action is not available in this scene.")
                run.revision += 1
            run.updated_at = datetime.now(UTC)
            await self.session.flush()
            return profile, run

    def enter_combat(self, profile, run):
        if run.floor == 10:
            raise DungeonUnavailable("At the Memory Core you are the Witness, not a combatant.")
        player = Fighter.snapshot(profile, "Your soul")
        player.hp, player.mp = run.hp, run.mp
        # Enhancement scales the existing offense, only in dungeon combat.
        from dataclasses import replace

        player.rule = replace(player.rule, damage_scale=player.rule.damage_scale * (1 + profile.weapon_level * 0.035))
        enemy = enemy_fighter(run.floor, run.encounter, profile.alignment)
        combat = DungeonCombat(player, enemy, run.seed + run.floor * 100 + run.encounter,
                               floor=run.floor, encounter=run.encounter)
        run.phase = "combat"
        run.state = dict(guild_id=run.state["guild_id"], battle=combat.export())

    def advance(self, profile, run):
        if run.state.get("sequence") == "opening":
            scene = run.state.get("scene", 0)
            if scene + 1 < len(OPENING):
                run.state = dict(run.state, scene=scene + 1)
            else:
                run.state = dict(guild_id=run.state["guild_id"], story_version=STORY_VERSION)
        elif run.phase in {"intro", "story"}:
            beat = run.state.get("story_beat", 1)
            scene = run.state.get("lore_scene", 0)
            scenes = lore_scenes(world_for(run.floor), run.phase, profile.alignment, beat)
            if scene + 1 < len(scenes):
                run.state = dict(run.state, lore_scene=scene + 1)
            elif run.phase == "intro":
                self.enter_combat(profile, run)
            elif beat == 2:
                run.encounter, run.phase = 3, "boss_intro"
                run.state = dict(guild_id=run.state["guild_id"])
            else:
                run.encounter = beat + 1
                self.enter_combat(profile, run)
        elif run.phase == "boss_intro":
            self.enter_combat(profile, run)
        elif run.phase == "victory":
            run.phase = "story"
            run.state = dict(guild_id=run.state["guild_id"], story_beat=run.encounter, lore_scene=0)
        elif run.phase == "cleared":
            run.floor += 1
            run.encounter = 0
            run.hp, run.mp = profile.max_hp, profile.max_mp
            run.phase = "seal" if run.floor == 10 else "intro"
            run.state = dict(guild_id=run.state["guild_id"], scene=0, sequence="core" if run.floor == 10 else "world", story_version=STORY_VERSION)
            profile.highest_floor = max(profile.highest_floor, run.floor)
        elif run.phase == "seal":
            scene = run.state.get("scene", 0)
            sequence = run.state.get("sequence", "core")
            if sequence == "choice":
                raise DungeonUnavailable("Choose the worldline you stand with.")
            scenes = ending_scenes(profile.ending_route) if sequence == "ending" else CORE
            flags = set(run.state.get("reveals", ())) | set(scenes[scene].reveal_flags)
            if scenes[scene].anchor:
                run.state = dict(run.state, anchors_released=scenes[scene].anchor)
            if scene + 1 < len(scenes):
                run.state = dict(run.state, scene=scene + 1, reveals=sorted(flags))
            elif sequence == "core":
                run.state = dict(run.state, sequence="choice", scene=0, reveals=sorted(flags))
            else:
                # The Floor 10 boss confrontation is cinematic. Its one-time
                # reward uses the same soul fields, never player cosmic stats.
                before = profile.weapon_level
                reward = award_xp(profile, 700 if before < 10 else 0)
                profile.weapon_level, profile.highest_floor = 10, 10
                profile.ending_completed_at = datetime.now(UTC)
                reward.update(weapon_before=before, weapon_after=10)
                run.phase, run.hp, run.mp = "complete", 0, 0
                run.state = dict(guild_id=run.state["guild_id"], reward=reward,
                                 sequence="finished", scene=0, reveals=sorted(flags), cycle=CYCLE)
        else:
            raise DungeonUnavailable("Finish this encounter before continuing.")

    async def combat_turn(self, profile, run, action):
        if run.floor == 10:
            raise DungeonUnavailable("This old battle has ended. Open `/dungeon` for the Memory Core.")
        combat = DungeonCombat.restore(run.state["battle"], run.seed + run.floor * 100 + run.encounter,
                                       run.floor, run.encounter)
        if action == "ability" and not combat.state.left.signature:
            raise DungeonUnavailable("Your saved signature has no supported combat effect.")
        state = combat.player_turn(action)
        run.hp, run.mp = state.left.hp, state.left.mp
        guild_id = run.state["guild_id"]
        run.state = dict(guild_id=guild_id, battle=combat.export())
        if not state.finished:
            return
        if state.winner_id != profile.user_id:
            run.phase, run.hp, run.mp = "defeated", 0, 0
            run.state = dict(guild_id=guild_id, log=state.log[-4:])
            await self.record_encounter(profile, run, state, guild_id, {})
            return
        await self.reward_victory(profile, run, state, guild_id)

    async def reward_victory(self, profile, run, state, guild_id, *, owner_skip=False):
        if run.floor == 10:
            raise DungeonUnavailable("The Memory Core concludes through the permanent worldline choice.")
        boss = run.encounter == 3
        if boss and profile.weapon_level != run.floor - 1:
            raise DungeonStale("This world's guardian reward was already claimed.")
        world = world_for(run.floor)
        amount = world.xp(run.encounter)
        reward = award_xp(profile, amount)
        if owner_skip:
            reward["owner_skip"] = True
        # Grow maximum resources without fully healing dungeon attrition.
        run.hp = min(profile.max_hp, run.hp + reward["gains"]["max_hp"])
        run.mp = min(profile.max_mp, run.mp + reward["gains"]["max_mp"])
        reward.update(weapon_before=profile.weapon_level, weapon_after=profile.weapon_level)
        if boss:
            profile.weapon_level += 1
            profile.highest_floor = max(profile.highest_floor, run.floor)
            reward["weapon_after"] = profile.weapon_level
            reward["anchors_released"] = profile.weapon_level
            reward["erasure_access"] = profile.weapon_level / 10
            run.phase = "cleared"
        else:
            run.phase = "victory"
        run.state = dict(guild_id=guild_id, reward=reward)
        await self.record_encounter(profile, run, state, guild_id, reward)

    async def record_encounter(self, profile, run, state, guild_id, reward):
        battle_id = sha256(f"{run.token}:{run.floor}:{run.encounter}".encode()).hexdigest()[:32]
        await FantasyDuelRepository(self.session).record(dict(
            id=battle_id, guild_id=guild_id, challenger_id=profile.user_id,
            opponent_id=state.right.user_id, winner_id=state.winner_id, seed=state.seed,
            rules_version=RULES_VERSION, rounds=max(1, min(6, state.round)), arena=world_for(run.floor).name,
            summary=dict(encounter="dungeon", floor=run.floor, enemy=state.right.name,
                         actual_rounds=state.round, reward=reward),
        ))
