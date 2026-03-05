"""
Twilio WebSocket handler — Deepgram streaming STT pipeline.

STT: Deepgram Nova-2 (streaming, real-time endpointing)
LLM: GPT-4o-mini (sentence-level streaming)
TTS: Rime.ai

Switch to this pipeline by pointing your Twilio webhook at:
  POST /deepgram/incoming-call
"""

import asyncio
import base64
import json
import ssl

import certifi
import websockets
from fastapi import APIRouter, Request, Response
from fastapi.websockets import WebSocket
from loguru import logger as log

from core.agent import ConversationAgent
from core.settings import settings
from services.tts import synthesize_speech
from services.webhook import post_call_data

router = APIRouter(tags=["Twilio-Deepgram"])

# Deepgram streaming STT — mulaw 8kHz matches Twilio's audio format exactly
DEEPGRAM_URL = (
    "wss://api.deepgram.com/v1/listen"
    "?model=nova-2"
    "&encoding=mulaw"
    "&sample_rate=8000"
    "&channels=1"
    "&punctuate=true"
    "&endpointing=300"
)

AUDIO_CHUNK_SIZE = 8192


# ---------------------------------------------------------------------------
# Twilio entry point
# ---------------------------------------------------------------------------

@router.api_route("/incoming-call", methods=["GET", "POST", "HEAD"])
def incoming_call(request: Request) -> Response:
    host = request.headers.get("Host")
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="wss://{host}/deepgram/media-stream" />
    </Connect>
</Response>"""
    return Response(content=twiml, media_type="application/xml")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _send_audio_to_twilio(
    websocket: WebSocket, stream_sid: str, audio_bytes: bytes
) -> None:
    for i in range(0, len(audio_bytes), AUDIO_CHUNK_SIZE):
        chunk = audio_bytes[i : i + AUDIO_CHUNK_SIZE]
        await websocket.send_text(
            json.dumps({
                "event": "media",
                "streamSid": stream_sid,
                "media": {"payload": base64.b64encode(chunk).decode()},
            })
        )


# ---------------------------------------------------------------------------
# Main WebSocket handler
# ---------------------------------------------------------------------------

@router.websocket("/media-stream")
async def media_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    log.info("[DEEPGRAM] Call connected")

    deepgram_ws = None
    deepgram_task: asyncio.Task | None = None
    stream_sid: str | None = None
    agent = ConversationAgent()
    current_response_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Inner: stream one transcript through LLM → TTS → Twilio
    # ------------------------------------------------------------------
    async def run_response(transcript: str) -> None:
        log.info(f"[STT] {transcript}")
        try:
            async for sentence in agent.respond_stream(transcript):
                log.info(f"[LLM] {sentence}")
                try:
                    audio = await synthesize_speech(sentence)
                    await _send_audio_to_twilio(websocket, stream_sid, audio)
                except Exception as tts_exc:
                    log.error(f"[TTS] Failed: {tts_exc}")
        except Exception as exc:
            log.error(f"Error during response: {exc}")
        finally:
            if agent.order.is_complete:
                log.info(f"[ORDER]\n{agent.order.summary()}")

    # ------------------------------------------------------------------
    # Inner: read Deepgram final transcripts and spawn response tasks
    # ------------------------------------------------------------------
    async def listen_to_deepgram(dg_ws) -> None:
        nonlocal current_response_task
        async for raw in dg_ws:
            data = json.loads(raw)

            if not data.get("is_final"):
                continue

            try:
                transcript: str = data["channel"]["alternatives"][0]["transcript"]
            except (KeyError, IndexError):
                continue

            if not transcript.strip():
                continue

            if current_response_task and not current_response_task.done():
                current_response_task.cancel()

            current_response_task = asyncio.create_task(run_response(transcript))

    # ------------------------------------------------------------------
    # Main event loop
    # ------------------------------------------------------------------
    try:
        while True:
            message = await websocket.receive()

            if "text" not in message:
                continue

            data = json.loads(message["text"])
            event = data.get("event")

            # --------------------------------------------------------------
            # START
            # --------------------------------------------------------------
            if event == "start":
                stream_sid = data["start"]["streamSid"]
                log.info(f"[DEEPGRAM] Stream started: {stream_sid}")

                greeting = agent.get_greeting()
                log.info(f"[DEEPGRAM] Greeting: {greeting}")

                ssl_ctx = ssl.create_default_context(cafile=certifi.where())
                deepgram_ws, greeting_audio = await asyncio.gather(
                    websockets.connect(
                        DEEPGRAM_URL,
                        additional_headers={
                            "Authorization": f"Token {settings.deepgram_auth}"
                        },
                        ssl=ssl_ctx,
                    ),
                    synthesize_speech(greeting),
                )

                deepgram_task = asyncio.create_task(listen_to_deepgram(deepgram_ws))

                try:
                    await _send_audio_to_twilio(websocket, stream_sid, greeting_audio)
                except Exception as exc:
                    log.error(f"[TTS] Greeting failed: {exc}")

            # --------------------------------------------------------------
            # MEDIA: forward audio to Deepgram
            # --------------------------------------------------------------
            elif event == "media" and deepgram_ws is not None:
                audio_bytes = base64.b64decode(data["media"]["payload"])
                await deepgram_ws.send(audio_bytes)

            # --------------------------------------------------------------
            # STOP
            # --------------------------------------------------------------
            elif event == "stop":
                log.info("[DEEPGRAM] Stream stopped by Twilio")
                break

    except Exception as exc:
        log.warning(f"[DEEPGRAM] WebSocket closed unexpectedly: {exc}")

    finally:
        if current_response_task:
            current_response_task.cancel()
        if deepgram_task:
            deepgram_task.cancel()
        if deepgram_ws:
            await deepgram_ws.close()
        if agent.order.is_complete:
            log.info(f"FINAL ORDER:\n{agent.order.summary()}")
        if settings.webhook_url:
            await post_call_data(
                settings.webhook_url,
                agent.history,
                agent.order.summary() if agent.order.is_complete else None,
                agent.order.total() if agent.order.is_complete else None,
            )
        log.info("[DEEPGRAM] Call disconnected")
