import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
    GITHUB_ORG_NAME = os.getenv("GITHUB_ORG_NAME")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    
    SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
    SMTP_EMAIL = os.getenv("SMTP_EMAIL")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
    DAILY_RECEIVERS = os.getenv("DAILY_RECEIVERS")
    WEEKLY_RECEIVERS = os.getenv("WEEKLY_RECEIVERS")
    TEAM_MEMBERS = os.getenv("TEAM_MEMBERS", "")
    DEV_EMAILS = os.getenv("DEV_EMAILS", "{}")
    
    @classmethod
    def validate(cls):
        missing = []
        for key in ["GITHUB_TOKEN", "GITHUB_ORG_NAME", "SMTP_EMAIL", "SMTP_PASSWORD", "DAILY_RECEIVERS", "WEEKLY_RECEIVERS"]:
            if not getattr(cls, key):
                missing.append(key)
        
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
