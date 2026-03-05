import httpx
from loguru import logger as log


async def post_call_data(
    webhook_url: str,
    transcript: list[dict],
    order_summary: str | None,
    order_total: float | None,
) -> None:
    """
    POST structured call data to webhook_url after a call ends.

    Payload shape:
    {
        "transcript": [{"role": "user"|"assistant", "content": "..."}],
        "order": {"summary": "...", "total": 12.50} | null
    }
    """
    payload: dict = {
        "transcript": transcript,
        "order": (
            {"summary": order_summary, "total": order_total}
            if order_summary
            else None
        ),
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(webhook_url, json=payload)
            log.info(f"[WEBHOOK] Posted call data → HTTP {response.status_code}")
    except Exception as exc:
        log.error(f"[WEBHOOK] Failed to post call data: {exc}")
