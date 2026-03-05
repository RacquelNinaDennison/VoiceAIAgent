"""
Rime.ai TTS → Twilio-compatible mulaw 8kHz audio.

Pipeline:
  Rime HTTP API (JSON response with base64 audioContent)
    → base64.b64decode()  — decode to raw WAV bytes
    → miniaudio.decode()  — decodes WAV and resamples to 8000 Hz in one step
    → audioop.lin2ulaw()  — encodes linear16 PCM to mulaw
    → ready to base64 and stream to Twilio
"""

import asyncio
import audioop
import base64

import httpx
import miniaudio
from loguru import logger as log

from core.settings import settings

RIME_TTS_URL = "https://users.rime.ai/v1/rime-tts"
TWILIO_SAMPLE_RATE = 8000  # Twilio requires mulaw at 8000 Hz


async def _fetch_audio_from_rime(text: str) -> bytes:
    """POST to Rime TTS and return raw audio bytes (WAV decoded from base64 JSON response)."""
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            RIME_TTS_URL,
            headers={
                "Authorization": f"Bearer {settings.rime_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "speaker": "marsh",
                "text": text,
                "modelId": "mist",
                "samplingRate": 22050,
                "speedAlpha": 1.0,
                "reduceLatency": True,
            },
        )

        content_type = response.headers.get("content-type", "unknown")
        log.debug(f"[TTS] Rime response: HTTP {response.status_code} | content-type: {content_type} | size: {len(response.content)} bytes")

        response.raise_for_status()

        # Rime returns JSON with a base64-encoded audioContent field
        if "application/json" in content_type or response.content[:1] == b"{":
            data = response.json()
            if "audioContent" not in data:
                raise ValueError(f"Rime JSON missing audioContent: {response.text[:200]}")
            return base64.b64decode(data["audioContent"])

        # Fallback: raw audio bytes
        return response.content


def _audio_to_mulaw_8k(audio_bytes: bytes) -> bytes:
    """
    Decode MP3 (or WAV/FLAC) and convert to mulaw 8000 Hz.
    miniaudio handles decoding + resampling in one pass.
    audioop-lts handles the linear16 → mulaw encoding.
    """
    decoded = miniaudio.decode(
        audio_bytes,
        output_format=miniaudio.SampleFormat.SIGNED16,
        nchannels=1,
        sample_rate=TWILIO_SAMPLE_RATE,
    )
    pcm_bytes = bytes(decoded.samples)
    return audioop.lin2ulaw(pcm_bytes, 2)


async def synthesize_speech(text: str) -> bytes:
    """
    Convert text to mulaw 8kHz bytes ready to stream to Twilio.
    Raises on failure — callers should handle exceptions gracefully.
    """
    log.debug(f"[TTS] synthesizing: {text[:80]}...")
    audio_bytes = await _fetch_audio_from_rime(text)
    # Run CPU-bound decode+conversion in a thread so the event loop stays free
    # to handle WebSocket keepalive pings while audio is being processed
    mulaw_bytes = await asyncio.to_thread(_audio_to_mulaw_8k, audio_bytes)
    log.debug(f"[TTS] {len(text)} chars → {len(mulaw_bytes)} mulaw bytes")
    return mulaw_bytes
