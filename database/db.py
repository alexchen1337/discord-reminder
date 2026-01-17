from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from .models import Base
import config


def get_engine():
    """Create engine with appropriate settings for the database type"""
    db_url = config.DATABASE_URL
    
    # PostgreSQL (Supabase) - use NullPool for serverless/external connections
    if db_url.startswith("postgresql"):
        return create_async_engine(
            db_url,
            echo=False,
            poolclass=NullPool,  # better for external DB connections
        )
    
    # SQLite (local development)
    return create_async_engine(db_url, echo=False)


engine = get_engine()
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session

