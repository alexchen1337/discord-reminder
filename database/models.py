from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    discord_user_id = Column(String, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    google_accounts = relationship("GoogleAccount", back_populates="user", cascade="all, delete-orphan")
    sent_reminders = relationship("SentReminder", back_populates="user", cascade="all, delete-orphan")


class GoogleAccount(Base):
    __tablename__ = "google_accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    discord_user_id = Column(String, ForeignKey("users.discord_user_id"), nullable=False)
    account_email = Column(String, nullable=False)
    refresh_token = Column(Text, nullable=False)  # encrypted
    access_token = Column(Text, nullable=True)  # encrypted
    token_expires_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="google_accounts")


class SentReminder(Base):
    __tablename__ = "sent_reminders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    discord_user_id = Column(String, ForeignKey("users.discord_user_id"), nullable=False)
    reminder_type = Column(String, nullable=False)  # 'daily_summary', 'hour_before'
    event_id = Column(String, nullable=False)  # Google event ID
    scheduled_time = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="sent_reminders")

