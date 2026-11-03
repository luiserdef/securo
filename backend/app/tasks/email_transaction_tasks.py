from datetime import date
from app.providers.google_gmail import GmailMessagesData
from app.models.transaction import Transaction
from app.services import transaction_service
import asyncio

from sqlalchemy import select,text
from app.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.worker import celery_app
from app.core.config import get_settings
import logging
logger = logging.getLogger(__name__)

devMode = 1

def _make_session_maker():
    """Create a fresh engine+session for the Celery worker event loop."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    # engine = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/securo"
    return engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def test_db():
    engine, session_maker = _make_session_maker()

    try:
        async with session_maker() as session:
            result = await session.execute(text("SELECT 1"))
            print("RESULT:", result.scalar())
    finally:
        await engine.dispose()

async def _generate_transactions_from_email() -> dict:
    count = 0
    try:
        scriptMode ="backend" 

        engine, session_maker = _make_session_maker()
        async with session_maker() as session:
            result = await session.execute(select(User.id))
            user_ids = [row[0] for row in result.all()]  

        for user_id in user_ids:
            async with session_maker() as session:
                count = await transaction_service.sync_transactions_email(session,user_id,mode=scriptMode)
  
        if count:
            # logger.info("Generated %d sync transactions for user %s", count, user_id)
            print("Generated sync transactions for user", count)

    except Exception as e:
        print(e)
        # logger.exception("Failed to sync email transactions for user %s", user_id)   

        return count


if __name__ == "__main__":
    total = asyncio.run(_generate_transactions_from_email()) 
    logger.info("Recurring generation complete: %d transactions created", total)
