from __future__ import annotations

from bot.services.voice_diagnostics import VoiceDiagnostics


def test_voice_diagnostics_tracks_and_formats_counters() -> None:
    diagnostics = VoiceDiagnostics()
    diagnostics.increment("rtp_packets")
    diagnostics.increment("gemini_input_chunks", 3)

    assert diagnostics.snapshot()["rtp_packets"] == 1
    report = diagnostics.format_snapshot(connected=True, dave_session_ready=True)
    assert "connected=True" in report
    assert "rtp_packets=1" in report
    assert "gemini_input_chunks=3" in report
