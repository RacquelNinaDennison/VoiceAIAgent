from fastapi import FastAPI, Request
from uvicorn import run
from routers.twillio import router as twillio_router
from middleware import RequestLoggingMiddleware
from fastapi.middleware.cors import CORSMiddleware
from middleware.logging import setup_uvicorn_loggers
from loguru import logger as log

app = FastAPI()
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(CORSMiddleware)
app.include_router(twillio_router, prefix="/twillio")


@app.get("/health")
def health_check():
    return {"message": "OK"}


@app.post("/webhook/call-complete")
async def call_complete_webhook(request: Request):
    """
    Built-in webhook receiver for post-call data.
    Set WEBHOOK_URL=http://localhost:8000/webhook/call-complete in .env to use this
    without an external service. Logs the payload and returns 200.
    """
    payload = await request.json()
    transcript = payload.get("transcript", [])
    order = payload.get("order")

    log.info(f"[WEBHOOK] Call complete — {len(transcript)} turns")
    if order:
        log.info(f"[WEBHOOK] Order total: £{order.get('total', 0):.2f}")
        log.info(f"[WEBHOOK] Order summary:\n{order.get('summary', '')}")
    else:
        log.info("[WEBHOOK] No order placed this call")

    return {"received": True}


def main():
    log.info("Starting Rime API server")
    setup_uvicorn_loggers()
    run(
        "api:app",
        host="0.0.0.0",
        port=8000,
        access_log=False,
        log_config=None,
        reload=True,
    )


if __name__ == "__main__":
    main()
