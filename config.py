import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8080/callback")
GOOGLE_SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def get_database_url() -> str:
    """Get database URL, converting Supabase format to asyncpg if needed"""
    url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///bot.db")
    
    # convert postgresql:// to postgresql+asyncpg:// for async support
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    
    return url


DATABASE_URL = get_database_url()

ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

DAILY_REMINDER_HOUR = 8  # 8 AM
REMINDER_DAYS_AHEAD = 7
HOUR_BEFORE_CHECK_INTERVAL = 5  # minutes
ANNOUNCEMENT_CHECK_INTERVAL = 30  # minutes

