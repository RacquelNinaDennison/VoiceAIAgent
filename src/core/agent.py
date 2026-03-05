import json
import re
from typing import AsyncGenerator

from openai import AsyncOpenAI
from loguru import logger as log

from core.restaurant import Order, build_system_prompt, load_agent_config
from core.settings import settings

OPENAI_MODEL = "gpt-4o-mini"

# Matches whitespace that follows sentence-ending punctuation.
# Used to split a streaming buffer into complete sentences.
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")

# Minimum characters before we consider a buffer ending in punctuation as a
# complete sentence ready for TTS (avoids flushing "Hi." prematurely).
_MIN_SENTENCE_CHARS = 12


def _flush_sentences(buffer: str) -> tuple[list[str], str]:
    """
    Extract all complete sentences from buffer.
    Returns (complete_sentences, remainder_still_in_progress).

    Two ways a sentence is considered complete:
    1. Punctuation followed by whitespace (mid-stream split)
    2. Buffer ends with sentence-ending punctuation and is long enough
       (catches the final sentence before a trailing space arrives)
    """
    parts = _SENTENCE_BOUNDARY.split(buffer)
    if len(parts) > 1:
        return [p.strip() for p in parts[:-1] if p.strip()], parts[-1]

    # No space-after-punctuation yet — but if the buffer ends with punctuation
    # and is substantial enough, treat it as a complete sentence now rather than
    # waiting for the next token. This eliminates one round-trip of latency for
    # every sentence in the response.
    stripped = buffer.strip()
    if len(stripped) >= _MIN_SENTENCE_CHARS and stripped[-1] in ".!?":
        return [stripped], ""

    return [], buffer


class ConversationAgent:
    """
    Manages a single phone call conversation.
    One instance per call — holds history and order state.
    Config can be supplied directly or loaded from AGENT_CONFIG_PATH.
    """

    def __init__(self, config: dict | None = None) -> None:
        self.config = config or load_agent_config(settings.agent_config_path)
        self.client = AsyncOpenAI(api_key=settings.openai_auth)
        self.system_prompt = build_system_prompt(self.config)
        self.history: list[dict] = []
        self.order = Order()

    def get_greeting(self) -> str:
        return self.config.get(
            "greeting",
            f"Hello, thank you for calling {self.config.get('restaurant_name', 'us')}!",
        )

    async def respond_stream(self, user_message: str) -> AsyncGenerator[str, None]:
        """
        Stream the agent's response sentence by sentence.

        Yields individual sentences as soon as they are complete so the caller
        can pipeline each sentence into TTS without waiting for the full reply.
        ORDER_COMPLETE is silently consumed and the order state is updated on
        self.order — callers should check self.order.is_complete after iteration.
        """
        self.history.append({"role": "user", "content": user_message})

        stream = await self.client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": self.system_prompt},
                *self.history,
            ],
            max_tokens=300,
            temperature=0.7,
            stream=True,
        )

        buffer = ""
        full_response = ""

        async for chunk in stream:
            token = chunk.choices[0].delta.content or ""
            if not token:
                continue

            buffer += token
            full_response += token

            # Once ORDER_COMPLETE appears, flush the spoken part before it
            # and drain the rest of the stream silently.
            if "ORDER_COMPLETE:" in buffer:
                pre_order = buffer.split("ORDER_COMPLETE:")[0]
                sentences, remainder = _flush_sentences(pre_order)
                for s in sentences:
                    if s.strip():
                        yield s.strip()
                if remainder.strip():
                    yield remainder.strip()
                buffer = ""
                # Drain remaining tokens into full_response only (not spoken)
                async for remaining_chunk in stream:
                    full_response += remaining_chunk.choices[0].delta.content or ""
                break

            sentences, buffer = _flush_sentences(buffer)
            for s in sentences:
                if s.strip():
                    yield s.strip()

        # Flush whatever is still in the buffer (final sentence without trailing space)
        remaining = buffer.strip()
        if remaining and "ORDER_COMPLETE" not in remaining:
            yield remaining

        # Persist the full assistant turn to history
        self.history.append({"role": "assistant", "content": full_response})
        log.debug(f"[LLM raw] {full_response}")

        # Parse order completion signal
        if "ORDER_COMPLETE:" in full_response:
            try:
                raw_json = full_response.split("ORDER_COMPLETE:", 1)[1].strip()
                # Trim anything after the closing bracket
                bracket_end = raw_json.rfind("]") + 1
                if bracket_end > 0:
                    raw_json = raw_json[:bracket_end]
                items: list[dict] = json.loads(raw_json)
                for item_data in items:
                    self.order.add_item(
                        name=item_data["item"],
                        price=float(item_data["price"]),
                        qty=int(item_data.get("qty", 1)),
                    )
                self.order.is_complete = True
                log.info(f"Order finalised:\n{self.order.summary()}")
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                log.warning(f"Could not parse ORDER_COMPLETE JSON: {e}")
