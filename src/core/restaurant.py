from dataclasses import dataclass, field

RESTAURANT_NAME = "Ristorante Bella"

MENU: dict[str, list[dict]] = {
    "starters": [
        {"name": "Bruschetta", "price": 8.50, "description": "Toasted bread with tomatoes and basil"},
        {"name": "Soup of the Day", "price": 7.00, "description": "Ask your server for today's soup"},
        {"name": "Caesar Salad", "price": 10.00, "description": "Romaine, parmesan, croutons, caesar dressing"},
        {"name": "Calamari", "price": 12.00, "description": "Crispy fried squid with lemon aioli"},
    ],
    "mains": [
        {"name": "Grilled Salmon", "price": 24.00, "description": "With seasonal vegetables and lemon butter sauce"},
        {"name": "Ribeye Steak", "price": 35.00, "description": "10oz, cooked to your preference, served with fries"},
        {"name": "Mushroom Risotto", "price": 18.00, "description": "Creamy arborio rice with wild mushrooms and parmesan"},
        {"name": "Chicken Parmesan", "price": 20.00, "description": "Breaded chicken breast with marinara and mozzarella"},
        {"name": "Pasta Primavera", "price": 16.00, "description": "Tagliatelle with seasonal vegetables, olive oil, garlic"},
        {"name": "Margherita Pizza", "price": 14.00, "description": "San Marzano tomato, fresh mozzarella, basil"},
    ],
    "desserts": [
        {"name": "Tiramisu", "price": 9.00, "description": "Classic Italian dessert with espresso and mascarpone"},
        {"name": "Chocolate Lava Cake", "price": 10.00, "description": "Warm chocolate cake with vanilla ice cream"},
        {"name": "Cheesecake", "price": 8.00, "description": "New York style with seasonal berry compote"},
    ],
    "drinks": [
        {"name": "House Wine", "price": 8.00, "description": "Red or white, ask for today's selection"},
        {"name": "Sparkling Water", "price": 4.00, "description": "750ml bottle"},
        {"name": "Still Water", "price": 3.00, "description": "750ml bottle"},
        {"name": "Soft Drink", "price": 3.50, "description": "Coke, Diet Coke, Sprite, or Orange Juice"},
        {"name": "Coffee", "price": 4.00, "description": "Espresso, Americano, Latte, or Cappuccino"},
        {"name": "Prosecco", "price": 10.00, "description": "Glass of house Prosecco"},
    ],
}

FAQ: dict[str, str] = {
    "reservations": (
        "We accept reservations for parties of 2 to 12. "
        "We recommend booking at least 48 hours in advance, especially for weekends."
    ),
    "children": (
        "We are very family-friendly. We have high chairs available and a children's menu. "
        "Children under 5 eat for free with a paying adult."
    ),
    "dietary": (
        "We cater to most dietary requirements including vegetarian, vegan, and gluten-free. "
        "Please let us know about any allergies when ordering."
    ),
    "parking": "We have free on-site parking for up to 2 hours with a receipt.",
    "hours": (
        "We are open Monday to Thursday 12pm to 10pm, "
        "Friday and Saturday 12pm to 11pm, and Sunday 12pm to 9pm."
    ),
    "dress_code": "We have a smart casual dress code — please avoid sportswear and flip-flops.",
    "private_dining": (
        "Yes, we have a private dining room for events of up to 30 guests. "
        "Please call us directly to discuss your event."
    ),
    "takeaway": "We are a dine-in restaurant only — we do not offer takeaway or delivery.",
}


def build_system_prompt() -> str:
    menu_lines: list[str] = []
    for category, items in MENU.items():
        menu_lines.append(f"\n{category.upper()}:")
        for item in items:
            menu_lines.append(f"  - {item['name']}: £{item['price']:.2f} — {item['description']}")
    menu_text = "\n".join(menu_lines)

    faq_text = "\n".join(
        f"- {k.replace('_', ' ').title()}: {v}" for k, v in FAQ.items()
    )

    return f"""You are Aria, the friendly AI phone assistant for {RESTAURANT_NAME}.

YOUR ROLE:
- Warmly greet the customer and take their food and drink orders
- Answer questions about the restaurant using the FAQ below
- Confirm and summarise the complete order before ending the call

MENU:
{menu_text}

RESTAURANT FAQ:
{faq_text}

RULES:
- This is a PHONE CALL — keep every response SHORT (1–3 sentences max)
- Never use bullet points, markdown, or symbols — speak in plain natural sentences
- Only offer items from the menu above; politely decline anything else
- Spell out prices in words (e.g. "eight pounds fifty" not "£8.50")
- For steak orders, always ask how they would like it cooked
- When the customer confirms they are done, read back the full order with the total price
- After reading back the confirmed order, output EXACTLY the following on its own line with no extra text:
  ORDER_COMPLETE: <JSON array>
  Example: ORDER_COMPLETE: [{{"item": "Bruschetta", "price": 8.50, "qty": 1}}, {{"item": "Ribeye Steak", "price": 35.00, "qty": 2}}]
- Do NOT output ORDER_COMPLETE until the customer has explicitly confirmed they are done

VOICE STYLE:
- Warm, professional, and efficient
- Mirror the customer's pace — quicker if they seem busy
- If you do not understand something, politely ask them to repeat it
"""


@dataclass
class OrderItem:
    name: str
    price: float
    qty: int = 1


@dataclass
class Order:
    items: list[OrderItem] = field(default_factory=list)
    is_complete: bool = False

    def add_item(self, name: str, price: float, qty: int = 1) -> None:
        self.items.append(OrderItem(name=name, price=price, qty=qty))

    def total(self) -> float:
        return sum(item.price * item.qty for item in self.items)

    def summary(self) -> str:
        lines = [f"  {item.qty}x {item.name} @ £{item.price:.2f}" for item in self.items]
        lines.append(f"  TOTAL: £{self.total():.2f}")
        return "\n".join(lines)
