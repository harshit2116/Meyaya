"""Runtime orchestration for Discord VC <-> Gemini Live audio conversations."""

from __future__ import annotations

import asyncio
from collections import deque
import logging
import threading
import time
from io import BytesIO

try:
    import audioop  # Python <= 3.12
except ImportError:  # pragma: no cover - Python >= 3.13
    import audioop_lts as audioop

import discord
from sqlalchemy.exc import SQLAlchemyError

from bot.app import MeyayaBot
from bot.prompts.composer import build_voice_system_instruction
from bot.repositories.server_lore import ServerLoreRepository
from bot.services.audio import (
    PcmStreamAudioSource,
    ResampleState,
    discord_pcm_48k_stereo_to_gemini_pcm_16k_mono,
    gemini_pcm_24k_mono_to_discord_pcm_48k_stereo,
)
from bot.services.gemini_live import GeminiLiveSession
from bot.services.meyaya_system import MeyayaSystemService
from bot.services.voice_diagnostics import VoiceDiagnostics
from bot.logging.telemetry import event

logger = logging.getLogger(__name__)

SPEECH_RMS_THRESHOLD = 800
SPEECH_CONFIRM_FRAMES = 5  # roughly 100 ms at Discord's 20 ms frame size

try:
    from discord.ext import voice_recv
except ImportError:  # pragma: no cover - optional dependency
    voice_recv = None


# `VoiceRecvClient.listen()` validates the sink with ``isinstance`` rather
# than duck-typing it, so implementing the same methods is not enough.
_AudioSinkBase = voice_recv.AudioSink if voice_recv is not None else object


class DiscordAudioReceiveSink(_AudioSinkBase):  # type: ignore[misc,valid-type]
    """Audio sink compatible with discord-ext-voice-recv AudioSink interface."""

    def __init__(self, owner: "VoiceChatSession") -> None:
        super().__init__()
        self.owner = owner
        self._state = ResampleState()
        self._consecutive_speech_frames = 0
        self._utterance_active = False
        self._pre_roll: deque[bytes] = deque(maxlen=SPEECH_CONFIRM_FRAMES)
        self._utterance_lock = threading.RLock()
        self._speaker_id = None
        self._speaker_last_audio = 0.0

    def wants_opus(self) -> bool:
        return False

    def write(self, user: discord.Member | discord.User | None, data) -> None:
        if not getattr(self.owner, "listening_enabled", True) or getattr(
            self.owner, "_song_playing", False
        ):
            return
        with self._utterance_lock:
            self._write_speaker(user, data)

    def _write_speaker(self, user, data) -> None:
        self.owner.note_received_frame(user, data)
        if user is None or user.bot:
            return
        if self.owner.bot.chat_blacklist.is_blocked(self.owner.guild_id, user.id):
            return

        pcm = getattr(data, "pcm", None)
        if not pcm:
            return

        # Fast local speech detection for barge-in/playback cut.
        try:
            rms = audioop.rms(pcm, 2)
        except Exception:
            rms = 0

        now = time.monotonic()
        if self._speaker_id is not None and now - self._speaker_last_audio > 1.2:
            self.end_utterance()
        if self._speaker_id is None:
            if rms < SPEECH_RMS_THRESHOLD:
                return
            self._speaker_id = user.id
        if self._speaker_id != user.id:
            return
        if rms >= SPEECH_RMS_THRESHOLD:
            self._speaker_last_audio = now

        if rms >= SPEECH_RMS_THRESHOLD:
            self._consecutive_speech_frames += 1
        else:
            self._consecutive_speech_frames = 0

        if self._consecutive_speech_frames >= SPEECH_CONFIRM_FRAMES:
            self.owner.diagnostics.increment("speech_frames")
            self.owner.notify_user_speaking(user)

        try:
            pcm16 = discord_pcm_48k_stereo_to_gemini_pcm_16k_mono(pcm, self._state)
            self.owner.note_resample(pcm16)
            chunks: list[bytes] = []
            with self._utterance_lock:
                if not self._utterance_active:
                    self._pre_roll.append(pcm16)
                    if self._consecutive_speech_frames >= SPEECH_CONFIRM_FRAMES:
                        self._utterance_active = True
                        chunks.extend(self._pre_roll)
                        self._pre_roll.clear()
                else:
                    chunks.append(pcm16)

            for chunk in chunks:
                self.owner.enqueue_user_audio(chunk)
        except Exception:
            logger.exception("Audio conversion failed for incoming Discord PCM")

    def end_utterance(self) -> None:
        """Pause forwarding after the active speaker has gone quiet."""

        with self._utterance_lock:
            self._utterance_active = False
            self._pre_roll.clear()
            self._consecutive_speech_frames = 0
            self._speaker_id = None
            self._state = ResampleState()

    def cleanup(self) -> None:
        return


class VoiceChatSession:
    """One live voice chat session per guild."""

    def __init__(self, bot: MeyayaBot, guild_id: int, *, voice_name: str | None = None) -> None:
        self.bot = bot
        self.guild_id = guild_id
        self.voice_name = voice_name or bot.settings.gemini_voice
        self.voice_client: discord.VoiceClient | None = None
        self.diagnostics = VoiceDiagnostics()
        self.play_source = PcmStreamAudioSource(self._note_playback_frame)
        self._playback_state = ResampleState()
        self._gemini: GeminiLiveSession | None = None
        self._closed = False
        self._loop = asyncio.get_running_loop()
        self._sink = DiscordAudioReceiveSink(self)
        self._last_end_sent_at = 0.0
        self._end_of_utterance_handle: asyncio.TimerHandle | None = None
        self._user_is_speaking = False
        self._received_discord_audio = False
        self._logged_resample = False
        self._song_playing = False
        self.listening_enabled = True
        self._voice_budget_task = None
        self._voice_budget_registered = False

    @property
    def connected_channel_id(self) -> int | None:
        if self.voice_client and self.voice_client.channel:
            return self.voice_client.channel.id
        return None

    @property
    def is_active(self) -> bool:
        """Return whether Discord and Gemini are both ready for this session."""

        return bool(
            not self._closed
            and self._gemini is not None
            and self.voice_client is not None
            and self.voice_client.is_connected()
        )

    async def connect_and_start(self, channel: discord.VoiceChannel | discord.StageChannel) -> None:
        if voice_recv is None:
            raise RuntimeError(
                "discord-ext-voice-recv is not installed. Install it to enable voice receiving."
            )

        if self.bot.settings.gemini_api_key == "":
            raise RuntimeError("GEMINI_API_KEY is missing")

        if not self._voice_budget_registered:
            await self.bot.ai_guard.start_voice(self.guild_id)
            self._voice_budget_registered = True
            self._voice_budget_task = asyncio.create_task(self._watch_voice_budget())

        if self.voice_client is None or not self.voice_client.is_connected():
            self.voice_client = await channel.connect(cls=voice_recv.VoiceRecvClient)
        elif self.voice_client.channel and self.voice_client.channel.id != channel.id:
            await self.voice_client.move_to(channel)

        assert self.voice_client is not None
        state_lines = await self._load_meyaya_state_lines(channel)
        self._gemini = GeminiLiveSession(
            guild_id=channel.guild.id,
            channel_id=channel.id,
            api_key=self.bot.settings.gemini_api_key,
            model=self.bot.settings.gemini_live_model,
            voice_name=self.voice_name,
            system_instruction=build_voice_system_instruction(
                extra_instruction=self.bot.settings.gemini_live_system_instruction,
                state_lines=state_lines,
            ),
            on_output_audio=self._on_gemini_audio,
            on_interrupted=self._on_gemini_interrupted,
            on_input_audio_sent=self._on_gemini_input_sent,
            on_reconnected=self._on_gemini_reconnected,
        )
        await self._gemini.start()

        # Start Gemini before enabling Discord receive. Discord can send RTP as
        # soon as listen() is called; starting it first avoids dropping that
        # initial user speech while the Live WebSocket is still connecting.
        self.voice_client.listen(self._sink)

        if not self.voice_client.is_playing():
            self.voice_client.play(
                self.play_source,
                after=lambda err: logger.error("Voice playback error: %s", err) if err else None,
            )

        logger.info(
            "[VOICE] connected guild=%s channel=%s model=%s voice=%s",
            self.guild_id,
            channel.id,
            self.bot.settings.gemini_live_model,
            self.voice_name,
        )
        self._log_dave_state()
        event('voice.joined', guild_id=self.guild_id, channel_id=channel.id)

    async def _watch_voice_budget(self):
        """Bound session duration, including silent/paused sessions."""
        try:
            for minute in range(1, self.bot.settings.voice_session_minutes + 1):
                await asyncio.sleep(60)
                if self._closed:
                    return
                if minute >= self.bot.settings.voice_session_minutes:
                    break
        except asyncio.CancelledError:
            return
        except Exception:
            logger.warning("Voice session timer failed guild=%s", self.guild_id)
        await self.close(reason="voice session duration reached")

    async def close(self, *, reason: str = "requested") -> None:
        if self._closed:
            return
        self._closed = True
        event('voice.left', guild_id=self.guild_id, channel_id=self.connected_channel_id)
        if self._voice_budget_task and self._voice_budget_task is not asyncio.current_task():
            self._voice_budget_task.cancel()

        logger.info("Stopping voice chat session guild=%s reason=%s", self.guild_id, reason)

        if self._gemini is not None:
            try:
                await self._gemini.stop()
            except Exception:
                logger.exception("Voice provider shutdown failed")
            self._gemini = None

        self.play_source.close()

        if self._end_of_utterance_handle is not None:
            self._end_of_utterance_handle.cancel()
            self._end_of_utterance_handle = None

        if self.voice_client is not None:
            try:
                if hasattr(self.voice_client, "stop_listening"):
                    self.voice_client.stop_listening()
            except Exception:
                logger.exception("Error while stopping voice listening")

            try:
                if self.voice_client.is_connected():
                    await self.voice_client.disconnect(force=True)
            except Exception:
                logger.exception("Error while disconnecting voice client")

            self.voice_client = None

        if self._voice_budget_registered:
            self.bot.ai_guard.end_voice(self.guild_id)
            self._voice_budget_registered = False

    def enqueue_user_audio(self, pcm16: bytes) -> None:
        if self._closed or self._gemini is None or self._song_playing or not self.listening_enabled:
            return
        if not self._received_discord_audio:
            self._received_discord_audio = True
            logger.info("Received first Discord voice PCM frame for Gemini")
        self._gemini.enqueue_audio_from_thread(pcm16)

    def note_resample(self, pcm16: bytes) -> None:
        if not self._logged_resample:
            self._logged_resample = True
            logger.info(
                "[RESAMPLE] input_rate=48000 input_channels=2 output_rate=16000 "
                "output_channels=1 bytes=%s",
                len(pcm16),
            )

    async def _on_gemini_input_sent(self, _: int) -> None:
        self.diagnostics.increment("gemini_input_chunks")

    async def _on_gemini_reconnected(self) -> None:
        """Reset local turn state after Gemini replaces a failed WebSocket."""

        self.diagnostics.increment("reconnects")
        self._user_is_speaking = False
        self._sink.end_utterance()
        if self._end_of_utterance_handle is not None:
            self._end_of_utterance_handle.cancel()
            self._end_of_utterance_handle = None
        logger.info("[VOICE] Gemini connection recovered; ready for the next utterance")

    def note_received_frame(self, user: discord.Member | discord.User | None, data) -> None:
        """Record frames that have completed native DAVE and Opus processing."""

        self.diagnostics.increment("rtp_packets")
        packet = getattr(data, "packet", None)
        ssrc = getattr(packet, "ssrc", None)
        if user is None:
            logger.debug("[RX] SSRC unresolved ssrc=%s", ssrc)
            return

        pcm = getattr(data, "pcm", b"")
        if not pcm:
            self.diagnostics.increment("opus_failures")
            return

        self.diagnostics.increment("dave_success")
        self.diagnostics.increment("opus_success")
        self.diagnostics.increment("pcm_frames")
        if self.diagnostics.snapshot().get("pcm_frames") == 1:
            logger.info(
                "[RX] RTP_PACKET_RECEIVED ssrc=%s USER_ID_RESOLVED user=%s "
                "DAVE_DECRYPT_SUCCESS OPUS_DECODE_SUCCESS PCM_FRAME_RECEIVED bytes=%s",
                ssrc,
                user.id,
                len(pcm),
            )

    def _note_playback_frame(self) -> None:
        self.diagnostics.increment("playback_frames")

    def _log_dave_state(self) -> None:
        state = getattr(self.voice_client, "_connection", None)
        session = getattr(state, "dave_session", None)
        logger.info(
            "[DAVE] session present=%s ready=%s protocol=%s",
            session is not None,
            bool(getattr(session, "ready", False)),
            getattr(state, "dave_protocol_version", 0),
        )

    def diagnostic_report(self) -> str:
        state = getattr(self.voice_client, "_connection", None)
        session = getattr(state, "dave_session", None)
        return self.diagnostics.format_snapshot(
            guild=self.guild_id,
            connected=bool(self.voice_client and self.voice_client.is_connected()),
            dave_session_present=session is not None,
            dave_session_ready=bool(getattr(session, "ready", False)),
            dave_protocol=getattr(state, "dave_protocol_version", 0),
        )

    async def run_voice_check(self) -> None:
        """Verify Gemini output and Discord playback without microphone input."""

        if self._song_playing:
            raise RuntimeError("Wait until the song finishes before checking voice")
        if self._closed or self._gemini is None:
            raise RuntimeError("No active Gemini Live session")
        await self._gemini.send_text(
            "Say exactly: Voice connection is working. Do not add anything else."
        )

    async def reply_to_text(self, user_id: int, message: str) -> None:
        if await self.bot.chat_blacklist.inspect(self.guild_id, user_id, message):
            return
        if self._song_playing:
            raise RuntimeError("A song is playing; try again when it finishes")
        if not self.is_active or self._gemini is None:
            raise RuntimeError("Voice session is not connected")
        await self._gemini.send_text(
            f"A member (Discord ID {user_id}) sent this text to the voice conversation. "
            f"Reply aloud, briefly and naturally: {message}"
        )

    async def set_listening(self, enabled: bool) -> None:
        self.listening_enabled = enabled
        self._sink.end_utterance()
        self._user_is_speaking = False
        if self._end_of_utterance_handle is not None:
            self._end_of_utterance_handle.cancel()
            self._end_of_utterance_handle = None
        if not enabled and self._gemini is not None:
            self._gemini.clear_input_audio()
            await self._gemini.signal_audio_end()

    async def play_song(self, audio: bytes, *, executable: str = "ffmpeg") -> None:
        """Stream decoded music into Discord, then resume the conversation source."""
        if not self.is_active or self._song_playing:
            raise RuntimeError("Voice is unavailable or a song is already playing")
        client = self.voice_client
        finished = asyncio.get_running_loop().create_future()
        source = discord.FFmpegPCMAudio(
            BytesIO(audio),
            pipe=True,
            executable=executable,
            before_options="-nostdin -loglevel error",
            options="-vn -t 90",
        )
        self._song_playing = True
        self._sink.end_utterance()
        if self._end_of_utterance_handle is not None:
            self._end_of_utterance_handle.cancel()
            self._end_of_utterance_handle = None
        self._user_is_speaking = False
        self.play_source.clear()

        def complete(error):
            if not finished.done():
                if error:
                    finished.set_exception(RuntimeError("Song playback failed"))
                else:
                    finished.set_result(None)

        try:
            # VoiceRecvClient.stop() also disables the microphone receiver.
            client.stop_playing()
            client.play(
                source, after=lambda error: self._loop.call_soon_threadsafe(complete, error)
            )
            event('voice.playback.started', guild_id=self.guild_id, channel_id=self.connected_channel_id)
            await asyncio.wait_for(finished, timeout=100)
        finally:
            client.stop_playing()
            event('voice.playback.stopped', guild_id=self.guild_id, channel_id=self.connected_channel_id)
            source.cleanup()
            self.play_source.clear()
            self._playback_state = ResampleState()
            self._sink.end_utterance()
            self._song_playing = False
            if not self._closed and client.is_connected():
                client.play(
                    self.play_source,
                    after=lambda error: (
                        logger.error("Voice playback error: %s", error) if error else None
                    ),
                )

    def notify_user_speaking(self, user: discord.Member | discord.User) -> None:
        """Handle speech from the receive thread on the bot's asyncio loop."""

        if self._closed:
            return

        self._loop.call_soon_threadsafe(
            self._on_user_speaking,
            user.id,
        )

    def _on_user_speaking(self, user_id: int) -> None:
        """Reset the utterance timer and interrupt audio once per utterance."""

        if self._closed or self._song_playing or not self.listening_enabled:
            return

        # Discord does not reliably provide silent PCM packets after a person stops
        # speaking.  Schedule the end ourselves so Gemini receives an explicit turn
        # boundary even when the receive stream goes quiet completely.
        if self._end_of_utterance_handle is not None:
            self._end_of_utterance_handle.cancel()
        self._end_of_utterance_handle = self._loop.call_later(1.2, self._on_silence_timeout)

        if self._user_is_speaking:
            return
        self._user_is_speaking = True
        self.diagnostics.increment("interruptions")
        asyncio.create_task(
            self._record_voice_conversation(user_id),
            name=f"meyaya-voice-state-{user_id}",
        )

        # Barge-in only needs to discard queued model audio. VoiceRecvClient.stop()
        # stops BOTH playback and inbound listening, which made the receiver go
        # deaf after the first human PCM frame. Keep the continuous AudioSource
        # alive; it naturally emits silence after its queue is cleared.
        if self.play_source.has_pending_audio():
            self.play_source.clear()
            logger.info("[VAD] sustained human speech detected; queued playback cleared")

    def _on_silence_timeout(self) -> None:
        self._end_of_utterance_handle = None
        self._user_is_speaking = False
        self._sink.end_utterance()
        self.notify_end_of_utterance()

    def notify_end_of_utterance(self) -> None:
        if self._closed or self._gemini is None:
            return
        now = time.time()
        if now - self._last_end_sent_at < 0.4:
            return
        self._last_end_sent_at = now
        asyncio.run_coroutine_threadsafe(self._gemini.signal_audio_end(), self._loop)

    async def _on_gemini_audio(self, pcm24: bytes) -> None:
        if self._closed or self._song_playing:
            return
        try:
            pcm48 = gemini_pcm_24k_mono_to_discord_pcm_48k_stereo(
                pcm24,
                self._playback_state,
            )
            self.play_source.push(pcm48)
            self.diagnostics.increment("gemini_output_chunks")
            if self.diagnostics.snapshot().get("gemini_output_chunks") == 1:
                logger.info("[PLAYBACK] first Gemini PCM chunk queued bytes=%s", len(pcm48))
        except Exception:
            logger.exception("Failed to convert Gemini output audio for Discord playback")

    async def _on_gemini_interrupted(self) -> None:
        # Server detected interruption; clear pending playback to align with latest turn.
        self.play_source.clear()

    async def _load_meyaya_state_lines(
        self, channel: discord.VoiceChannel | discord.StageChannel
    ) -> list[str]:
        """Load current mood and relationships for members present when VC starts."""

        members = [(member.id, member.display_name) for member in channel.members if not member.bot]
        try:
            async with self.bot.db_session() as session:
                service = MeyayaSystemService(session)
                lines = await service.voice_prompt_lines(self.guild_id, members)
                lore = await ServerLoreRepository(session).list_current(self.guild_id, limit=12)
                if lore:
                    lines.append(
                        "Shared server lore and inside jokes. Reference these only when naturally "
                        "relevant:\n" + "\n".join(f"- {item.content}" for item in lore)
                    )
                return lines
        except SQLAlchemyError:
            logger.exception("Meyaya System state unavailable for voice; using base persona")
            return []

    async def _record_voice_conversation(self, user_id: int) -> None:
        """Update familiarity once when a member begins a voice utterance."""

        try:
            async with self.bot.db_session() as session:
                service = MeyayaSystemService(session)
                guild = self.bot.get_guild(self.guild_id)
                member = guild.get_member(user_id) if guild else None
                await service.record_conversation(
                    self.guild_id,
                    user_id,
                    display_name=member.display_name if member else None,
                )
                await session.commit()
        except SQLAlchemyError:
            logger.exception("Failed to update Meyaya System voice familiarity")
