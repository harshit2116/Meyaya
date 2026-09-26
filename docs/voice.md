# Voice chat

Normal written commands (for example `uwu profile` and `uwu ship @one @two`) and slash commands can be used in a voice channel's text chat while Meyaya is connected. Mention her or reply to her message for a normal written conversation; use `voice <message>` for a spoken reply. Her View Channel and Send Messages permissions are required. Server chat bindings still apply: admins can run `uwu chatbind channel` inside the voice channel's text chat to bind conversation there, or `uwu chatbind server` to allow it across the server. `/chatbind` also accepts voice and stage channels.

- Join a Discord voice channel and run `uwu join`.
- Use `uwu voice "hello Meyaya"` to send text and hear her reply aloud. Quotes are optional. You must be in her voice channel. `/voice message:hello` also works.
- Use `uwu voiceset` to browse all 30 supported studio voices in selectable menus, with style descriptions. Manage Server is required. Selecting a voice disconnects and reconnects an active session in the same channel immediately, preserving microphone listening on/off. `uwu voiceset Leda` and `/voiceset` also work; `uwu voiceset default` restores the configured default. If not connected, the selection applies to the next `join`. Voice overrides reset when the bot restarts. If reconnecting fails, use `join` again.
- Use `uwu voicecheck` to test speech output; `uwu leave` disconnects.
- Use `uwu listen off` to stop forwarding microphone audio while staying connected; `uwu listen on` resumes it. `uwu listen status` shows the setting. Members in the current channel or server managers can control it. Each new session starts with listening on. Typed voice requests still work when listening is off.
- Meyaya automatically leaves after the channel has no human members for three minutes (checked every 15 seconds). A returning member resets the timer. Bots do not keep her connected.

During overlapping speech, the first audible speaker holds the input until 1.2 seconds of silence. Other simultaneous speech is ignored, not transcribed or queued. Conversion state resets between speakers to avoid splicing different streams together.



Normal live conversation does not require the archived song-generation feature. FFmpeg is installed for audio decoding, but there is currently no public song playback command.

For Windows audio tooling, `FFMPEG_EXECUTABLE` can point to the local executable. Do not copy that Windows path into Azure's Linux environment; the Docker image uses `FFMPEG_EXECUTABLE=ffmpeg` instead.

Recent text chat logs showed provider timeouts. A full timeout now returns control to the router immediately; ordinary chat can fall back once to the configured reasoning model. This improves recovery but cannot repair provider outages or exhausted quotas.
The singing command is archived and is not registered or available in help. Archived generation code is retained only for reference; no music API requests run through Discord commands.
