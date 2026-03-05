import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    def __init__(self):
        self.rime_api_key = os.getenv("RIME_API_KEY")
        self.twillio_auth = os.getenv("TWILLIO_AUTH")
        self.deepgram_auth = os.getenv("DEEPGRAM_AUTH")
        self.openai_auth = os.getenv("OPENAI_AUTH")
        self.twillio_account_sid = os.getenv("TWILLIO_ACCOUNT_SID")


settings = Settings()
