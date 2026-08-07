"""Base Repository"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from motor.motor_asyncio import AsyncDatabase
from bson import ObjectId


class BaseRepository(ABC):
    """Base repository for database operations"""

    def __init__(self, db: AsyncDatabase, collection_name: str):
        self.db = db
        self.collection = db[collection_name]

    async def create(self, data: Dict[str, Any]) -> str:
        """Create a document"""
        result = await self.collection.insert_one(data)
        return str(result.inserted_id)

    async def get_by_id(self, id: str) -> Optional[Dict]:
        """Get document by ID"""
        try:
            return await self.collection.find_one({"_id": ObjectId(id)})
        except Exception:
            return None

    async def update_by_id(self, id: str, data: Dict[str, Any]) -> bool:
        """Update document by ID"""
        try:
            result = await self.collection.update_one(
                {"_id": ObjectId(id)}, {"$set": data}
            )
            return result.modified_count > 0
        except Exception:
            return False

    async def delete_by_id(self, id: str) -> bool:
        """Delete document by ID"""
        try:
            result = await self.collection.delete_one({"_id": ObjectId(id)})
            return result.deleted_count > 0
        except Exception:
            return False

    async def list_all(
        self, skip: int = 0, limit: int = 10, filter_dict: Dict = None
    ) -> List[Dict]:
        """List documents with pagination"""
        query = filter_dict or {}
        cursor = self.collection.find(query).skip(skip).limit(limit)
        return await cursor.to_list(length=limit)

    async def count(self, filter_dict: Dict = None) -> int:
        """Count documents"""
        query = filter_dict or {}
        return await self.collection.count_documents(query)
