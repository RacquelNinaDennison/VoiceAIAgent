"""
OpenAI Whisper transcription service.

Converts Twilio's mulaw 8kHz audio buffer to a WAV file in memory
and sends it to the Whisper API for transcription.
"""

import audioop
import io
import wave

from loguru import logger as log
from openai import AsyncOpenAI

from core.settings import settings

_client = AsyncOpenAI(api_key=settings.openai_auth)


async def transcribe(mulaw_bytes: bytes) -> str:
    """
    Transcribe a mulaw 8kHz audio buffer using OpenAI Whisper.
    Returns the transcript string, or an empty string on failure.
    """
    # mulaw → linear16 PCM
    pcm = audioop.ulaw2lin(mulaw_bytes, 2)

    # Wrap in an in-memory WAV container — Whisper needs a proper audio format
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(8000)
        wf.writeframes(pcm)
    buf.seek(0)
    buf.name = "audio.wav"  # SDK uses the filename to detect format

    log.debug(f"[STT] Sending {len(mulaw_bytes)} mulaw bytes to Whisper")
    try:
        result = await _client.audio.transcriptions.create(
            model="whisper-1",
            file=buf,
            language="en",
        )
        return result.text
    except Exception as exc:
        log.error(f"[STT] Whisper failed: {exc}")
        return ""
