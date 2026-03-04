from fastapi import APIRouter
from fastapi import Request, Response
from fastapi.websockets import WebSocket
from loguru import logger as log

router = APIRouter(tags=["Twillio"])


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


# returns this websocket to twillio to stream the media
@router.websocket("/media-stream")
async def media_stream(websocket: WebSocket):
    await websocket.accept()
    log.info("call connected")
    try:
        while True:
            message = await websocket.receive()
            log.info(message)
    except Exception as e:
        log.warning(f"WebSocket closed: {e}")
    finally:
        log.info("call disconnected")
