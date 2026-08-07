"""User Repository"""
from typing import Optional, Dict, Any
from motor.motor_asyncio import AsyncDatabase
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository):
    """User repository for database operations"""

    def __init__(self, db: AsyncDatabase):
        super().__init__(db, "users")

    async def get_by_email(self, email: str) -> Optional[Dict]:
        """Get user by email"""
        return await self.collection.find_one({"email": email})

    async def email_exists(self, email: str) -> bool:
        """Check if email already exists"""
        user = await self.get_by_email(email)
        return user is not None

    async def create_user(self, data: Dict[str, Any]) -> str:
        """Create a new user"""
        return await self.create(data)

    async def get_user_by_id(self, user_id: str) -> Optional[Dict]:
        """Get user by ID"""
        return await self.get_by_id(user_id)
