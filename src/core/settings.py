import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    def __init__(self):
        self.rime_api_key = os.getenv("RIME_API_KEY")
        self.twillio_auth = os.getenv("TWILLIO_AUTH")
        self.deepgram_auth = os.getenv("DEEPGRAM_AUTH")
        self.gemini_auth = os.getenv("GEMINI_AUTH")
        self.openai_auth = os.getenv("OPENAI_AUTH")
        self.twillio_account_sid = os.getenv("TWILLIO_ACCOUNT_SID")
        # Optional: URL to POST call data to after each call ends
        self.webhook_url = os.getenv("WEBHOOK_URL")
        # Optional: path to a JSON file that defines the agent persona/menu/faq
        self.agent_config_path = os.getenv("AGENT_CONFIG_PATH")


settings = Settings()
