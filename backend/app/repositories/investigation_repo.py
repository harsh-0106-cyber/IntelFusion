"""Investigation Repository"""
from typing import Optional, Dict, Any, List
from motor.motor_asyncio import AsyncDatabase
from bson import ObjectId
from app.repositories.base import BaseRepository


class InvestigationRepository(BaseRepository):
    """Investigation repository for database operations"""

    def __init__(self, db: AsyncDatabase):
        super().__init__(db, "investigations")

    async def create_investigation(self, data: Dict[str, Any]) -> str:
        """Create a new investigation"""
        return await self.create(data)

    async def get_investigation_by_id(self, investigation_id: str) -> Optional[Dict]:
        """Get investigation by ID"""
        return await self.get_by_id(investigation_id)

    async def update_investigation(self, investigation_id: str, data: Dict[str, Any]) -> bool:
        """Update investigation"""
        return await self.update_by_id(investigation_id, data)

    async def delete_investigation(self, investigation_id: str) -> bool:
        """Delete investigation"""
        return await self.delete_by_id(investigation_id)

    async def get_investigations_by_user(
        self, user_id: str, skip: int = 0, limit: int = 10, status: Optional[str] = None
    ) -> List[Dict]:
        """Get investigations by user with optional status filter"""
        query = {"created_by": ObjectId(user_id)}
        if status:
            query["status"] = status
        return await self.list_all(skip=skip, limit=limit, filter_dict=query)

    async def count_investigations_by_user(self, user_id: str, status: Optional[str] = None) -> int:
        """Count investigations by user with optional status filter"""
        query = {"created_by": ObjectId(user_id)}
        if status:
            query["status"] = status
        return await self.count(query)

    async def search_investigations(
        self, user_id: str, search_query: str, skip: int = 0, limit: int = 10
    ) -> List[Dict]:
        """Search investigations by title or description"""
        query = {
            "created_by": ObjectId(user_id),
            "$or": [
                {"title": {"$regex": search_query, "$options": "i"}},
                {"description": {"$regex": search_query, "$options": "i"}},
            ],
        }
        return await self.list_all(skip=skip, limit=limit, filter_dict=query)

    async def add_seed_input(
        self, investigation_id: str, seed_input: Dict[str, Any]
    ) -> bool:
        """Add seed input to investigation"""
        try:
            result = await self.collection.update_one(
                {"_id": ObjectId(investigation_id)},
                {"$push": {"seed_inputs": seed_input}},
            )
            return result.modified_count > 0
        except Exception:
            return False


class AuditLogRepository(BaseRepository):
    """Audit Log repository for database operations"""

    def __init__(self, db: AsyncDatabase):
        super().__init__(db, "audit_logs")

    async def create_log(
        self,
        investigation_id: str,
        user_id: str,
        action: str,
        changes: Dict[str, Any] = None,
    ) -> str:
        """Create an audit log"""
        log_data = {
            "investigation_id": ObjectId(investigation_id),
            "user_id": ObjectId(user_id),
            "action": action,
            "changes": changes or {},
            "timestamp": None,  # MongoDB will use current timestamp
        }
        return await self.create(log_data)

    async def get_logs_by_investigation(
        self, investigation_id: str, skip: int = 0, limit: int = 50
    ) -> List[Dict]:
        """Get audit logs for investigation"""
        query = {"investigation_id": ObjectId(investigation_id)}
        cursor = (
            self.collection.find(query)
            .sort("timestamp", -1)
            .skip(skip)
            .limit(limit)
        )
        return await cursor.to_list(length=limit)
