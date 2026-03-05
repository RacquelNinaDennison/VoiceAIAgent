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


async def _respond_to_customer(
    transcript: str,
    websocket: WebSocket,
    stream_sid: str,
    agent: ConversationAgent,
) -> None:
    """LLM → TTS → Twilio. Runs as an asyncio task per utterance."""
    try:
        log.info(f"[STT] {transcript}")
        response_text, order_complete = await agent.respond(transcript)

        if not response_text:
            return

        log.info(f"[LLM] {response_text}")

        try:
            audio = await synthesize_speech(response_text)
            await _send_audio_to_twilio(websocket, stream_sid, audio)
        except Exception as tts_exc:
            log.error(f"[TTS] Failed: {tts_exc}")

        if order_complete:
            log.info(f"[ORDER]\n{agent.order.summary()}")

    except Exception as exc:
        log.error(f"Error during response: {exc}")


async def _listen_to_deepgram(
    deepgram_ws,
    websocket: WebSocket,
    stream_sid: str,
    agent: ConversationAgent,
) -> None:
    """
    Background task: reads Deepgram transcript messages and spawns a response
    task for each final utterance.
    """
    async for raw in deepgram_ws:
        data = json.loads(raw)

        if not data.get("is_final"):
            continue

        try:
            transcript: str = data["channel"]["alternatives"][0]["transcript"]
        except (KeyError, IndexError):
            continue

        if transcript.strip():
            asyncio.create_task(
                _respond_to_customer(transcript, websocket, stream_sid, agent)
            )


# ---------------------------------------------------------------------------
# Main WebSocket handler
# ---------------------------------------------------------------------------

@router.websocket("/media-stream")
async def media_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    log.info("Call connected")

    deepgram_ws = None
    deepgram_task = None
    stream_sid: str | None = None
    agent = ConversationAgent()

    try:
        while True:
            message = await websocket.receive()

            if "text" not in message:
                continue

            data = json.loads(message["text"])
            event = data.get("event")

            # ------------------------------------------------------------------
            # START: Twilio has connected the audio stream
            # ------------------------------------------------------------------
            if event == "start":
                stream_sid = data["start"]["streamSid"]
                log.info(f"Stream started: {stream_sid}")

                greeting = agent.get_greeting()
                log.info(f"[GREETING] {greeting}")

                # Kick off Deepgram connection and greeting TTS at the same time
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
                    _listen_to_deepgram(deepgram_ws, websocket, stream_sid, agent)
                )

                try:
                    await _send_audio_to_twilio(websocket, stream_sid, greeting_audio)
                except Exception as exc:
                    log.error(f"[TTS] Greeting failed: {exc}")

            # ------------------------------------------------------------------
            # MEDIA: forward raw audio bytes to Deepgram
            # ------------------------------------------------------------------
            elif event == "media" and deepgram_ws is not None:
                audio_bytes = base64.b64decode(data["media"]["payload"])
                await deepgram_ws.send(audio_bytes)

            # ------------------------------------------------------------------
            # STOP: caller hung up or Twilio ended the stream
            # ------------------------------------------------------------------
            elif event == "stop":
                log.info("Stream stopped by Twilio")
                break

    except Exception as exc:
        log.warning(f"WebSocket closed unexpectedly: {exc}")

    finally:
        if deepgram_task is not None:
            deepgram_task.cancel()
        if deepgram_ws is not None:
            await deepgram_ws.close()
        if agent.order.is_complete:
            log.info(f"FINAL ORDER:\n{agent.order.summary()}")
        log.info("Call disconnected")
