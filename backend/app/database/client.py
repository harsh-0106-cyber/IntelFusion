"""MongoDB Client"""
from motor.motor_asyncio import AsyncClient, AsyncDatabase
from app.config import settings


class MongoDB:
    """MongoDB connection handler"""
    client: AsyncClient = None
    db: AsyncDatabase = None


mongo_db = MongoDB()


async def connect_to_mongo():
    """Connect to MongoDB"""
    mongo_db.client = AsyncClient(settings.MONGODB_URL)
    mongo_db.db = mongo_db.client[settings.MONGODB_DB_NAME]
    print("Connected to MongoDB")


async def close_mongo_connection():
    """Close MongoDB connection"""
    if mongo_db.client:
        mongo_db.client.close()
        print("Closed MongoDB connection")


def get_database() -> AsyncDatabase:
    """Get database instance"""
    return mongo_db.db
