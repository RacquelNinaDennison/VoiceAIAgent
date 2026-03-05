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

router = APIRouter(tags=["Twilio"])

# Deepgram streaming STT — mulaw 8kHz matches Twilio's audio format exactly
DEEPGRAM_URL = (
    "wss://api.deepgram.com/v1/listen"
    "?model=nova-2"
    "&encoding=mulaw"
    "&sample_rate=8000"
    "&channels=1"
    "&punctuate=true"
    "&endpointing=300"   # 300ms silence = end of utterance
)

# Chunk size for streaming audio back to Twilio (~1s of mulaw at 8kHz)
AUDIO_CHUNK_SIZE = 8192



# ---------------------------------------------------------------------------
# Twilio entry point — returns TwiML that connects the call to our WebSocket
# ---------------------------------------------------------------------------

@router.api_route("/incoming-call", methods=["GET", "POST", "HEAD"])
def incoming_call(request: Request) -> Response:
    host = request.headers.get("Host")
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="wss://{host}/twillio/media-stream" />
    </Connect>
</Response>"""
    return Response(content=twiml, media_type="application/xml")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _send_audio_to_twilio(
    websocket: WebSocket, stream_sid: str, audio_bytes: bytes
) -> None:
    """Stream mulaw audio back to Twilio in chunks."""
    for i in range(0, len(audio_bytes), AUDIO_CHUNK_SIZE):
        chunk = audio_bytes[i : i + AUDIO_CHUNK_SIZE]
        payload = base64.b64encode(chunk).decode()
        await websocket.send_text(
            json.dumps({
                "event": "media",
                "streamSid": stream_sid,
                "media": {"payload": payload},
            })
        )



# ---------------------------------------------------------------------------
# Main WebSocket handler
# ---------------------------------------------------------------------------

@router.websocket("/media-stream")
async def media_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    log.info("Call connected")

    deepgram_ws = None
    deepgram_task: asyncio.Task | None = None
    stream_sid: str | None = None
    agent = ConversationAgent()

    # Tracks the currently active LLM→TTS→Twilio pipeline task so it can be
    # cancelled on barge-in or when a new transcript supersedes it.
    current_response_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Inner coroutine: pipeline one transcript through LLM → TTS → Twilio
    # Sentences are synthesised and sent one at a time as the LLM streams,
    # giving much lower perceived latency than waiting for the full reply.
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
    # Inner coroutine: read Deepgram transcripts and spawn response tasks
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

            # Cancel any in-progress response before starting the new one
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
            # START: Twilio has connected the audio stream
            # --------------------------------------------------------------
            if event == "start":
                stream_sid = data["start"]["streamSid"]
                log.info(f"Stream started: {stream_sid}")

                greeting = agent.get_greeting()
                log.info(f"[GREETING] {greeting}")

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

                deepgram_task = asyncio.create_task(
                    listen_to_deepgram(deepgram_ws)
                )

                try:
                    await _send_audio_to_twilio(websocket, stream_sid, greeting_audio)
                except Exception as exc:
                    log.error(f"[TTS] Greeting failed: {exc}")

            # --------------------------------------------------------------
            # MEDIA: forward raw audio bytes to Deepgram; detect barge-in
            # --------------------------------------------------------------
            elif event == "media" and deepgram_ws is not None:
                audio_bytes = base64.b64decode(data["media"]["payload"])
                await deepgram_ws.send(audio_bytes)

            # --------------------------------------------------------------
            # STOP: caller hung up or Twilio ended the stream
            # --------------------------------------------------------------
            elif event == "stop":
                log.info("Stream stopped by Twilio")
                break

    except Exception as exc:
        log.warning(f"WebSocket closed unexpectedly: {exc}")

    finally:
        if current_response_task:
            current_response_task.cancel()
        if deepgram_task:
            deepgram_task.cancel()
        if deepgram_ws:
            await deepgram_ws.close()

        if agent.order.is_complete:
            log.info(f"FINAL ORDER:\n{agent.order.summary()}")

        # Post call data to webhook if configured
        if settings.webhook_url:
            await post_call_data(
                settings.webhook_url,
                agent.history,
                agent.order.summary() if agent.order.is_complete else None,
                agent.order.total() if agent.order.is_complete else None,
            )

        log.info("Call disconnected")
