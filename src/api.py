from fastapi import FastAPI
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
