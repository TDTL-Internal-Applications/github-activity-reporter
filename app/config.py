import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
    GITHUB_ORG_NAME = os.getenv("GITHUB_ORG_NAME")
    
    SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
    SMTP_EMAIL = os.getenv("SMTP_EMAIL")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
    RECEIVER_EMAIL = os.getenv("RECEIVER_EMAIL")

    @classmethod
    def validate(cls):
        missing = []
        for key in ["GITHUB_TOKEN", "GITHUB_ORG_NAME", "SMTP_EMAIL", "SMTP_PASSWORD", "RECEIVER_EMAIL"]:
            if not getattr(cls, key):
                missing.append(key)
        
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
