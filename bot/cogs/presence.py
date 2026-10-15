"""A gentle presence rotation drawn from Meyaya's personality and Origin lore."""

import logging
from urllib.parse import urlsplit

import discord
from discord.ext import commands, tasks

logger = logging.getLogger(__name__)


STATUS_TEXT = "The Girl at the end of every story"
STATUS_EMOJI_ID = 1556562750409281637
ROTATION_MINUTES = 5

# Activity names follow Discord's Playing/Watching/Streaming label.
PRESENCES = (
    (discord.ActivityType.playing, "the final boss. I packed you snacks."),
    (discord.ActivityType.watching, "your villain arc. Needs more flowers."),
    (discord.ActivityType.streaming, "Origin.exe | endings are negotiable"),
    (discord.ActivityType.playing, "with fate. It blinked first."),
    (discord.ActivityType.watching, "the story you almost gave up on"),
    (discord.ActivityType.streaming, "the bloopers between your character arcs"),
    (discord.ActivityType.playing, "Origin Protocol: one more chance"),
    (discord.ActivityType.watching, "Veyra threaten reality. Again."),
    (discord.ActivityType.streaming, "the Tenfold Descent, with commentary"),
    (discord.ActivityType.playing, "matchmaker with suspicious confidence"),
    (discord.ActivityType.watching, "the quiet souls in a loud room"),
    (discord.ActivityType.streaming, "one more chance from the end of the story"),
)


def identity_activity() -> discord.CustomActivity:
    # Discord may omit custom-status emoji for bot presences.
    return discord.CustomActivity(
        name=STATUS_TEXT,
        emoji=discord.PartialEmoji(name="Meyaya", id=STATUS_EMOJI_ID),
    )


def presence_activities(stream_url=""):
    stream_url = stream_url.strip()
    if not stream_url:
        logger.info("Streaming statuses disabled: PRESENCE_STREAM_URL is not configured")
    if stream_url:
        try:
            parsed = urlsplit(stream_url)
            valid = (parsed.scheme == "https" and parsed.hostname in {
                "twitch.tv", "www.twitch.tv", "youtube.com", "www.youtube.com", "youtu.be",
            } and parsed.path not in {"", "/"} and not parsed.username
                and not any(char.isspace() for char in stream_url))
        except ValueError:
            valid = False
        if not valid:
            logger.warning("PRESENCE_STREAM_URL must be a Twitch or YouTube HTTPS link; skipping Streaming statuses")
            stream_url = ""
    activities = [identity_activity()]
    for kind, text in PRESENCES:
        if kind == discord.ActivityType.streaming:
            if stream_url:
                activities.append(discord.Streaming(name=text, url=stream_url))
        elif kind == discord.ActivityType.playing:
            activities.append(discord.Game(name=text))
        else:
            activities.append(discord.Activity(type=kind, name=text))
    return tuple(activities)


class PresenceCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.activities = presence_activities(
            getattr(getattr(bot, "settings", None), "presence_stream_url", "")
        )
        # Show a native activity immediately instead of appearing unchanged for
        # five minutes after every deployment. Keep the identity in the cycle.
        self.index = 1
        self._first_tick = True

    async def cog_load(self):
        # Extensions can also be reloaded after READY has already happened.
        if self.bot.is_ready():
            await self.on_ready()

    async def apply_presence(self):
        try:
            await self.bot.change_presence(
                status=discord.Status.dnd,
                activity=self.activities[self.index],
            )
            logger.info("presence_updated type=%s index=%s interval_minutes=%s",
                        self.activities[self.index].type.name, self.index, ROTATION_MINUTES)
        except (discord.HTTPException, ConnectionError, OSError) as error:
            logger.warning("Meyaya presence unavailable; will retry on the next rotation or reconnect (%s)",
                           type(error).__name__)

    @commands.Cog.listener()
    async def on_ready(self):
        await self.apply_presence()
        if not self.rotate.is_running():
            self._first_tick = True
            self.rotate.start()

    @commands.Cog.listener()
    async def on_resumed(self):
        # A successful gateway resume does not dispatch another READY event.
        await self.on_ready()

    @tasks.loop(minutes=ROTATION_MINUTES)
    async def rotate(self):
        # tasks.loop runs immediately; on_ready already applied this activity.
        if self._first_tick:
            self._first_tick = False
            return
        self.index = (self.index + 1) % len(self.activities)
        await self.apply_presence()

    def cog_unload(self):
        self.rotate.cancel()


async def setup(bot):
    await bot.add_cog(PresenceCog(bot))
