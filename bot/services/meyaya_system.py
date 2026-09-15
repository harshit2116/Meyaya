"""Mood, energy, and member relationship logic for the Meyaya System."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import re
from typing import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from bot.data.private_identity import PrivateIdentity, get_private_identity
from bot.models.meyaya_state import MeyayaGlobalState, MeyayaUserState
from bot.repositories.meyaya_state import MeyayaStateRepository

DEFAULT_ENERGY = 70
CHAT_FAMILIARITY_COOLDOWN = timedelta(minutes=2)
CHAT_FAMILIARITY_GAIN = 2
MOOD_LIFETIME_HOURS = 4

STRONG_HOSTILITY_PATTERNS = (
    re.compile(r"\b(?:fuck\s+(?:you|off)|shut\s+up|kill\s+yourself|kys)\b"),
    re.compile(r"\b(?:i\s+hate\s+you|bad\s+bot)\b"),
    re.compile(r"\byou(?:'re|\s+are)\s+(?:useless|worthless|pathetic|stupid|an\s+idiot)\b"),
)
RUDE_LANGUAGE_PATTERN = re.compile(
    r"\b(?:annoying|criminal|dumb|idiot|irritating|loser|moron|pathetic|stupid|"
    r"torture|trash|useless|worst)\b"
)
WARM_LANGUAGE_PATTERN = re.compile(
    r"\b(?:good\s+bot|love\s+you|thank\s+you|thanks|you(?:'re|\s+are)\s+"
    r"(?:amazing|cute|lovely|sweet))\b"
)
APOLOGY_PATTERN = re.compile(r"\b(?:i(?:'m|\s+am)\s+sorry|my\s+bad|sorry\s+meyaya)\b")


@dataclass(frozen=True, slots=True)
class InteractionEffect:
    familiarity: int = 1
    affection: int = 0
    user_annoyance: int = 0
    energy: int = 0
    global_annoyance: int = 0
    mood: str = "normal"


@dataclass(frozen=True, slots=True)
class ConversationEffect:
    """A bounded relationship change inferred from one direct chat message."""

    affection: int = 0
    user_annoyance: int = 0
    energy: int = 0
    global_annoyance: int = 0
    mood: str | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class MeyayaProfileState:
    """Display-ready mood and relationship state for a member profile."""

    mood: str
    energy: int
    global_annoyance: int
    relationship: str
    familiarity: int
    affection: int
    user_annoyance: int
    nickname: str | None
    is_parent: bool
    is_favorite: bool


INTERACTION_EFFECTS: dict[str, InteractionEffect] = {
    "hug": InteractionEffect(1, 3, -2, 2, -2, "happy"),
    "kiss": InteractionEffect(1, 4, -1, 2, -1, "happy"),
    "pat": InteractionEffect(1, 2, -2, 1, -1, "happy"),
    "headpat": InteractionEffect(1, 3, -2, 1, -2, "happy"),
    "cuddle": InteractionEffect(1, 4, -2, -1, -2, "happy"),
    "handhold": InteractionEffect(1, 3, -1, 0, -1, "happy"),
    "cheer": InteractionEffect(1, 2, -1, 4, -1, "happy"),
    "highfive": InteractionEffect(1, 2, -1, 4, -1, "happy"),
    "smile": InteractionEffect(1, 2, -1, 2, -1, "happy"),
    "slap": InteractionEffect(1, -2, 12, 5, 12, "annoyed"),
    "bonk": InteractionEffect(1, -1, 7, 4, 7, "annoyed"),
    "bite": InteractionEffect(1, 0, 5, 5, 5, "chaotic"),
    "poke": InteractionEffect(1, 0, 3, 2, 3, "annoyed"),
    "facepalm": InteractionEffect(1, 0, 4, -1, 4, "annoyed"),
    "tickle": InteractionEffect(1, 1, 2, 6, 1, "chaotic"),
    "dance": InteractionEffect(1, 2, -1, 7, -1, "chaotic"),
    "laugh": InteractionEffect(1, 1, -1, 5, -1, "chaotic"),
    "cry": InteractionEffect(1, 1, -1, -5, 0, "sleepy"),
}


class MeyayaSystemService:
    """Apply state transitions and turn current state into Gemini context."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.session = session
        self.states = MeyayaStateRepository(session)
        self.identity: PrivateIdentity = get_private_identity()
        self._now = now or (lambda: datetime.now(UTC))

    async def record_conversation(
        self,
        guild_id: int | None,
        user_id: int,
        content: str = "",
        relationship_signal: str | None = None,
    ) -> None:
        """Apply familiarity and bounded tone effects from a direct conversation."""

        scope_id = self._scope_id(guild_id)
        now = self._now()
        global_state = await self.states.get_or_create_global(scope_id)
        user_state = await self.states.get_or_create_user(scope_id, user_id)
        self._materialize_decay(global_state, user_state, now)

        last_seen = self._aware(user_state.last_interaction_at)
        if last_seen is None or now - last_seen >= CHAT_FAMILIARITY_COOLDOWN:
            user_state.familiarity = self._clamp(user_state.familiarity + CHAT_FAMILIARITY_GAIN)
            global_state.energy = self._clamp(global_state.energy + 1)
            global_state.energy_updated_at = now
            # This timestamp throttles counted familiarity gains. Updating it on
            # every message creates a sliding window that never completes while
            # someone is actively talking to Meyaya.
            user_state.last_interaction_at = now

        effect = self.conversation_effect(content, relationship_signal)
        user_state.affection = self._clamp(user_state.affection + effect.affection)
        user_state.annoyance = self._clamp(user_state.annoyance + effect.user_annoyance)
        global_state.energy = self._clamp(global_state.energy + effect.energy)
        global_state.annoyance = self._clamp(global_state.annoyance + effect.global_annoyance)
        if effect.user_annoyance:
            user_state.annoyance_updated_at = now
        if effect.global_annoyance:
            global_state.annoyance_updated_at = now
        if effect.mood is not None:
            global_state.mood = effect.mood
            global_state.mood_reason = (
                f"Discord user ID {user_id} {effect.reason or 'affected Meyaya in chat'}."
            )
            global_state.mood_changed_at = now
        global_state.updated_at = now
        self._assign_nickname_if_ready(user_state)
        await self.session.flush()

    @staticmethod
    def conversation_effect(
        content: str,
        relationship_signal: str | None = None,
    ) -> ConversationEffect:
        """Classify obvious direct warmth or hostility without another AI request."""

        signal_effects = {
            "neutral": ConversationEffect(),
            "kind": ConversationEffect(
                affection=2,
                user_annoyance=-4,
                energy=1,
                global_annoyance=-2,
                mood="happy",
                reason="was kind to her",
            ),
            "annoying": ConversationEffect(
                affection=-1,
                user_annoyance=5,
                energy=-1,
                global_annoyance=3,
                mood="annoyed",
                reason="was persistently teasing or irritating toward her",
            ),
            "rude": ConversationEffect(
                affection=-3,
                user_annoyance=10,
                energy=-2,
                global_annoyance=6,
                mood="annoyed",
                reason="was directly rude or hostile toward her",
            ),
        }
        normalized_signal = (
            relationship_signal.strip().casefold() if isinstance(relationship_signal, str) else None
        )
        if normalized_signal in signal_effects:
            return signal_effects[normalized_signal]

        normalized = " ".join(content.casefold().split())
        if not normalized:
            return ConversationEffect()

        strong_hits = sum(
            pattern.search(normalized) is not None for pattern in STRONG_HOSTILITY_PATTERNS
        )
        rude_hits = len(RUDE_LANGUAGE_PATTERN.findall(normalized))
        if strong_hits or rude_hits:
            annoyance = min(14, strong_hits * 10 + rude_hits * 3)
            return ConversationEffect(
                affection=-min(4, strong_hits * 3 + rude_hits),
                user_annoyance=annoyance,
                energy=-min(3, max(1, strong_hits + rude_hits)),
                global_annoyance=max(2, (annoyance + 1) // 2),
                mood="annoyed",
                reason="was rude or repeatedly irritating toward her",
            )

        if APOLOGY_PATTERN.search(normalized):
            return ConversationEffect(
                affection=2,
                user_annoyance=-6,
                energy=1,
                global_annoyance=-3,
                mood="happy",
                reason="apologized to her",
            )
        if WARM_LANGUAGE_PATTERN.search(normalized):
            return ConversationEffect(
                affection=2,
                user_annoyance=-3,
                energy=1,
                global_annoyance=-1,
                mood="happy",
                reason="was kind to her",
            )
        return ConversationEffect()

    async def apply_interaction(
        self,
        guild_id: int | None,
        user_id: int,
        interaction_name: str,
    ) -> None:
        """Apply an interaction directed at Meyaya to global and user state."""

        effect = INTERACTION_EFFECTS.get(interaction_name, InteractionEffect())
        scope_id = self._scope_id(guild_id)
        now = self._now()
        global_state = await self.states.get_or_create_global(scope_id)
        user_state = await self.states.get_or_create_user(scope_id, user_id)
        self._materialize_decay(global_state, user_state, now)

        user_state.familiarity = self._clamp(user_state.familiarity + effect.familiarity)
        user_state.affection = self._clamp(user_state.affection + effect.affection)
        user_state.annoyance = self._clamp(user_state.annoyance + effect.user_annoyance)
        self._assign_nickname_if_ready(user_state)
        user_state.last_interaction_at = now

        global_state.energy = self._clamp(global_state.energy + effect.energy)
        global_state.annoyance = self._clamp(global_state.annoyance + effect.global_annoyance)
        global_state.mood = effect.mood
        global_state.mood_reason = (
            f"Discord user ID {user_id} used {interaction_name} on Meyaya recently."
        )
        global_state.updated_at = now
        global_state.mood_changed_at = now
        global_state.energy_updated_at = now
        global_state.annoyance_updated_at = now
        user_state.annoyance_updated_at = now
        await self.session.flush()

    async def prompt_lines(
        self,
        guild_id: int | None,
        user_id: int,
        display_name: str,
    ) -> list[str]:
        """Describe effective global and relationship state for one text speaker."""

        scope_id = self._scope_id(guild_id)
        now = self._now()
        global_state = await self.states.get_global(scope_id)
        user_state = await self.states.get_user(scope_id, user_id)
        global_values = self._effective_global(global_state, now)
        user_values = self._effective_user(user_state, now)
        return self._format_prompt_lines(
            global_values,
            user_values,
            user_id=user_id,
            display_name=display_name,
        )

    async def profile_state(
        self,
        guild_id: int | None,
        user_id: int,
    ) -> MeyayaProfileState:
        """Return decayed state suitable for a public member profile."""

        scope_id = self._scope_id(guild_id)
        now = self._now()
        global_state = await self.states.get_global(scope_id)
        user_state = await self.states.get_user(scope_id, user_id)
        return self.profile_state_from_records(user_id, global_state, user_state, now=now)

    def profile_state_from_records(
        self,
        user_id: int,
        global_state: MeyayaGlobalState | None,
        user_state: MeyayaUserState | None,
        *,
        now: datetime | None = None,
    ) -> MeyayaProfileState:
        """Build public profile state from records loaded by a larger aggregate query."""

        current = now or self._now()
        mood, energy, global_annoyance, _ = self._effective_global(global_state, current)
        familiarity, affection, user_annoyance, nickname = self._relationship_values(
            user_id,
            self._effective_user(user_state, current),
        )
        return MeyayaProfileState(
            mood=mood,
            energy=energy,
            global_annoyance=global_annoyance,
            relationship=self._relationship_label_for_user(
                user_id, familiarity, affection, user_annoyance
            ),
            familiarity=familiarity,
            affection=affection,
            user_annoyance=user_annoyance,
            nickname=nickname,
            is_parent=self.identity.is_parent(user_id),
            is_favorite=self.identity.is_favorite(user_id),
        )

    async def voice_prompt_lines(
        self,
        guild_id: int,
        members: list[tuple[int, str]],
    ) -> list[str]:
        """Describe global state and known relationships for members currently in VC."""

        now = self._now()
        global_values = self._effective_global(await self.states.get_global(guild_id), now)
        mood, energy, annoyance, reason = global_values
        lines = [
            "THE MEYAYA SYSTEM is active for this voice conversation.",
            f"Current mood: {mood}; energy: {energy}/100; irritation: {annoyance}/100.",
        ]
        if reason:
            lines.append(f"Reason for the current mood: {reason}")

        visible_members = members[:20]
        user_states = await self.states.get_users(
            guild_id, [user_id for user_id, _ in visible_members]
        )
        relationship_lines = []
        for user_id, display_name in visible_members:
            values = self._relationship_values(
                user_id,
                self._effective_user(user_states.get(user_id), now),
            )
            familiarity, affection, user_annoyance, nickname = values
            relationship = self._relationship_label_for_user(
                user_id, familiarity, affection, user_annoyance
            )
            nickname_text = f', nickname "{nickname}"' if nickname else ""
            relationship_lines.append(
                f"- {display_name} (Discord ID {user_id}): {relationship}; familiarity "
                f"{familiarity}/100, affection {affection}/100, annoyance "
                f"{user_annoyance}/100{nickname_text}."
            )
        if relationship_lines:
            lines.append(
                "Relationships with members currently in voice:\n" + "\n".join(relationship_lines)
            )
        return lines

    async def command_for_intent(
        self,
        guild_id: int | None,
        user_id: int,
        intent: str,
    ) -> str | None:
        """Choose one harmless interaction command from relationship strength."""

        allowed_intents = {"comfort", "celebrate", "greet"}
        if intent not in allowed_intents:
            return None

        state = await self.states.get_user(self._scope_id(guild_id), user_id)
        familiarity, affection, annoyance, _ = self._relationship_values(
            user_id, self._effective_user(state, self._now())
        )

        if annoyance >= 65:
            return "wave" if intent == "greet" else None
        if intent == "greet":
            return "hug" if familiarity >= 70 and affection >= 45 else "wave"
        if intent == "celebrate":
            return "highfive" if familiarity >= 15 else "cheer"

        # Comfort becomes more physically affectionate only as Meyaya grows
        # familiar with and fond of the member.
        if familiarity >= 40 and affection >= 20:
            return "hug"
        if familiarity >= 12 or affection >= 8:
            return "pat"
        return "cheer"

    def _format_prompt_lines(
        self,
        global_values: tuple[str, int, int, str | None],
        user_values: tuple[int, int, int, str | None],
        *,
        user_id: int,
        display_name: str,
    ) -> list[str]:
        mood, energy, global_annoyance, reason = global_values
        familiarity, affection, user_annoyance, nickname = self._relationship_values(
            user_id, user_values
        )
        relationship = self._relationship_label_for_user(
            user_id, familiarity, affection, user_annoyance
        )
        lines = [
            "THE MEYAYA SYSTEM is active. Let this state subtly shape tone; never read these values aloud.",
            f"Current mood: {mood}; energy: {energy}/100; irritation: {global_annoyance}/100.",
            f"Relationship with {display_name} (Discord ID {user_id}): {relationship}.",
            f"Familiarity: {familiarity}/100; affection: {affection}/100; annoyance with them: {user_annoyance}/100.",
        ]
        if nickname:
            lines.append(f'Meyaya currently calls this member "{nickname}".')
        if reason:
            lines.append(f"Reason for the current mood: {reason}")
        return lines

    def _materialize_decay(
        self,
        global_state: MeyayaGlobalState,
        user_state: MeyayaUserState,
        now: datetime,
    ) -> None:
        mood, energy, annoyance, reason = self._effective_global(global_state, now)
        familiarity, affection, user_annoyance, nickname = self._effective_user(user_state, now)
        global_state.mood = mood
        global_state.energy = energy
        global_state.annoyance = annoyance
        global_state.mood_reason = reason
        if self._decay_amount(global_state.energy_updated_at, now, 3):
            global_state.energy_updated_at = now
        if self._decay_amount(global_state.annoyance_updated_at, now, 3):
            global_state.annoyance_updated_at = now
        if reason is None and global_state.mood_reason is not None:
            global_state.mood_changed_at = now
        user_state.familiarity = familiarity
        user_state.affection = affection
        user_state.annoyance = user_annoyance
        user_state.nickname = nickname
        if self._decay_amount(user_state.annoyance_updated_at, now, 2):
            user_state.annoyance_updated_at = now

    def _effective_global(
        self, state: MeyayaGlobalState | None, now: datetime
    ) -> tuple[str, int, int, str | None]:
        if state is None:
            return "normal", DEFAULT_ENERGY, 0, None
        mood_age_hours = self._age_hours(state.mood_changed_at, now)
        energy_decay = self._decay_amount(state.energy_updated_at, now, 3)
        annoyance_decay = self._decay_amount(state.annoyance_updated_at, now, 3)
        energy = self._move_toward(state.energy, DEFAULT_ENERGY, energy_decay)
        annoyance = self._clamp(state.annoyance - annoyance_decay)
        mood = state.mood
        reason = state.mood_reason
        if mood_age_hours >= MOOD_LIFETIME_HOURS:
            mood = self._resting_mood(energy, annoyance)
            reason = None
        return mood, energy, annoyance, reason

    def _effective_user(
        self, state: MeyayaUserState | None, now: datetime
    ) -> tuple[int, int, int, str | None]:
        if state is None:
            return 0, 0, 0, None
        annoyance = self._clamp(
            state.annoyance - self._decay_amount(state.annoyance_updated_at, now, 2)
        )
        return state.familiarity, state.affection, annoyance, state.nickname

    @staticmethod
    def _relationship_label(familiarity: int, affection: int, annoyance: int) -> str:
        if annoyance >= 65:
            return "a familiar rival who is seriously testing her patience"
        if annoyance >= 35:
            return "familiar, but currently getting on her nerves"
        if familiarity >= 80 and affection >= 60:
            return "very close and deeply liked"
        if familiarity >= 50:
            return "a familiar friend"
        if familiarity >= 20:
            return "a known acquaintance"
        return "still getting to know them"

    def _relationship_label_for_user(
        self,
        user_id: int,
        familiarity: int,
        affection: int,
        annoyance: int,
    ) -> str:
        if self.identity.is_parent(user_id):
            return "one of her parents and favorite people"
        if self.identity.is_favorite(user_id):
            return "one of her favorite people"
        return self._relationship_label(familiarity, affection, annoyance)

    def _relationship_values(
        self,
        user_id: int,
        values: tuple[int, int, int, str | None],
    ) -> tuple[int, int, int, str | None]:
        familiarity, affection, annoyance, nickname = values
        if self.identity.is_favorite(user_id):
            familiarity = 100
            affection = 100
        return familiarity, affection, annoyance, nickname

    @staticmethod
    def _resting_mood(energy: int, annoyance: int) -> str:
        if annoyance >= 50:
            return "annoyed"
        if energy <= 30:
            return "sleepy"
        if energy >= 90:
            return "chaotic"
        return "normal"

    @staticmethod
    def _assign_nickname_if_ready(state: MeyayaUserState) -> None:
        """Give a familiar member one stable nickname and remember it."""

        if state.nickname is not None:
            return
        if state.familiarity < 20 and state.affection < 12:
            return

        if state.annoyance >= 35:
            choices = ("Troublemaker", "Little Menace", "Chaos Gremlin", "Problem Child")
        elif state.affection >= 25:
            choices = ("Sunshine", "Sweetpea", "Lovebug", "Angel Bean")
        elif state.familiarity >= 50:
            choices = ("Bestie", "Star", "Buddy", "Mochi")
        else:
            choices = ("Bean", "Spark", "Mochi", "Bubbles")

        state.nickname = choices[state.user_id % len(choices)]

    @staticmethod
    def _scope_id(guild_id: int | None) -> int:
        return guild_id or 0

    @staticmethod
    def _clamp(value: int) -> int:
        return max(0, min(100, value))

    @staticmethod
    def _move_toward(value: int, target: int, amount: int) -> int:
        if value < target:
            return min(target, value + amount)
        return max(target, value - amount)

    @classmethod
    def _decay_amount(cls, value: datetime | None, now: datetime, amount_per_hour: int) -> int:
        return int(cls._age_hours(value, now) * amount_per_hour)

    @classmethod
    def _age_hours(cls, value: datetime | None, now: datetime) -> float:
        aware = cls._aware(value)
        if aware is None:
            return 0
        return max(0.0, (now - aware).total_seconds() / 3600)

    @staticmethod
    def _aware(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
