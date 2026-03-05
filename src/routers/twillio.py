from fastapi import APIRouter
from fastapi import Request, Response
from fastapi.websockets import WebSocket
from loguru import logger as log

import asyncio
import base64
import json
import ssl
import certifi
import websockets

from core.settings import settings

router = APIRouter(tags=["Twillio"])

DEEPGRAM_URL = (
    "wss://api.deepgram.com/v1/listen"
    "?encoding=mulaw"
    "&sample_rate=8000"
    "&channels=1"
    "&punctuate=true"
    "&endpointing=300"
)


async def listen_to_deepgram(deepgram_ws):
    """Background task: reads transcript messages from Deepgram and logs final results."""
    async for raw_message in deepgram_ws:
        data = json.loads(raw_message)
        is_final = data.get("is_final", False)
        try:
            transcript = data["channel"]["alternatives"][0]["transcript"]
        except (KeyError, IndexError):
            continue
        if is_final and transcript:
            log.info(f"Transcript: {transcript}")


@router.api_route("/incoming-call", methods=["GET", "POST", "HEAD"])
def incoming_call(request: Request):
    host = request.headers.get("Host")
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="wss://{host}/twillio/media-stream" />
    </Connect>
</Response>"""
    return Response(content=twiml, media_type="application/xml")


@router.websocket("/media-stream")
async def media_stream(websocket: WebSocket):
    await websocket.accept()
    log.info("Call connected")

    deepgram_ws = None
    deepgram_task = None

    try:
        while True:
            message = await websocket.receive()

            if "text" not in message:
                continue

            data = json.loads(message["text"])
            event = data.get("event")

            if event == "start":
                log.info("Twilio stream started — opening Deepgram connection")
                ssl_context = ssl.create_default_context(cafile=certifi.where())
                deepgram_ws = await websockets.connect(
                    DEEPGRAM_URL,
                    additional_headers={"Authorization": f"Token {settings.deepgram_auth}"},
                    ssl=ssl_context,
                )
                deepgram_task = asyncio.create_task(listen_to_deepgram(deepgram_ws))
                log.info("Deepgram connection open")

            elif event == "media" and deepgram_ws is not None:
                audio_bytes = base64.b64decode(data["media"]["payload"])
                await deepgram_ws.send(audio_bytes)

            elif event == "stop":
                log.info("Twilio stream stopped")
                break

    except Exception as e:
        log.warning(f"WebSocket closed: {e}")
    finally:
        if deepgram_task is not None:
            deepgram_task.cancel()
        if deepgram_ws is not None:
            await deepgram_ws.close()
        log.info("Call disconnected")
