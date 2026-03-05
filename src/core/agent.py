import json

from openai import AsyncOpenAI
from loguru import logger as log

from core.restaurant import Order, build_system_prompt
from core.settings import settings

OPENAI_MODEL = "gpt-4o-mini"


class ConversationAgent:
    """
    Manages a single phone call conversation.
    One instance per call — holds history and order state.
    """

    def __init__(self) -> None:
        self.client = AsyncOpenAI(api_key=settings.openai_auth)
        self.system_prompt = build_system_prompt()
        self.history: list[dict] = []
        self.order = Order()

    def get_greeting(self) -> str:
        return (
            "Thank you for calling Ristorante Bella! "
            "My name is Aria. How can I help you today?"
        )

    async def respond(self, user_message: str) -> tuple[str, bool]:
        """
        Process a customer utterance and return (spoken_response, order_is_complete).
        The ORDER_COMPLETE signal is stripped from the spoken response before returning.
        """
        self.history.append({"role": "user", "content": user_message})

        response = await self.client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": self.system_prompt},
                *self.history,
            ],
            max_tokens=300,
            temperature=0.7,
        )

        assistant_message = response.choices[0].message.content or ""
        self.history.append({"role": "assistant", "content": assistant_message})

        log.debug(f"[LLM raw] {assistant_message}")

        # Parse order completion signal
        order_complete = False
        spoken_response = assistant_message

        if "ORDER_COMPLETE:" in assistant_message:
            order_complete = True
            parts = assistant_message.split("ORDER_COMPLETE:", 1)
            spoken_response = parts[0].strip()

            try:
                order_json = parts[1].strip()
                items: list[dict] = json.loads(order_json)
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

        return spoken_response, order_complete
