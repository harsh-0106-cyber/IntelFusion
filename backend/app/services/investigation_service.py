"""Investigation Service"""
from typing import Optional, Dict, Tuple, List
from datetime import datetime, timezone
from bson import ObjectId
from motor.motor_asyncio import AsyncDatabase
from app.repositories.investigation_repo import (
    InvestigationRepository,
    AuditLogRepository,
)
from app.schemas.investigation import (
    InvestigationCreate,
    InvestigationUpdate,
    InvestigationResponse,
    InvestigationListResponse,
)
from app.utils.validators import (
    validate_seed_input_type,
    validate_investigation_status,
    validate_priority,
    sanitize_input,
)


class InvestigationService:
    """Investigation service"""

    def __init__(self, db: AsyncDatabase):
        self.investigation_repo = InvestigationRepository(db)
        self.audit_repo = AuditLogRepository(db)

    async def create_investigation(
        self, user_id: str, investigation_data: InvestigationCreate
    ) -> Tuple[bool, Optional[InvestigationResponse], Optional[str]]:
        """Create a new investigation"""
        # Validate priority
        if not validate_priority(investigation_data.priority):
            return False, None, "Invalid priority level"

        # Prepare data
        investigation_dict = {
            "title": sanitize_input(investigation_data.title),
            "description": sanitize_input(investigation_data.description),
            "status": "Draft",
            "priority": investigation_data.priority,
            "created_by": ObjectId(user_id),
            "seed_inputs": [],
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

        # Add seed inputs if provided
        if investigation_data.seed_inputs:
            for seed_input in investigation_data.seed_inputs:
                if not validate_seed_input_type(seed_input.type):
                    return False, None, f"Invalid seed input type: {seed_input.type}"
                investigation_dict["seed_inputs"].append(
                    {
                        "type": seed_input.type,
                        "value": sanitize_input(seed_input.value),
                        "added_at": datetime.now(timezone.utc),
                    }
                )

        try:
            investigation_id = await self.investigation_repo.create_investigation(
                investigation_dict
            )

            # Create audit log
            await self.audit_repo.create_log(
                investigation_id, user_id, "created", {"status": "Draft"}
            )

            # Prepare response
            investigation_dict["_id"] = investigation_id
            response = InvestigationResponse(**investigation_dict)
            return True, response, None
        except Exception as e:
            return False, None, str(e)

    async def get_investigation(
        self, investigation_id: str, user_id: str
    ) -> Tuple[bool, Optional[InvestigationResponse], Optional[str]]:
        """Get investigation by ID"""
        investigation = await self.investigation_repo.get_investigation_by_id(
            investigation_id
        )
        if not investigation:
            return False, None, "Investigation not found"

        # Check if user owns this investigation
        if str(investigation["created_by"]) != user_id:
            return False, None, "Unauthorized"

        response = InvestigationResponse(**investigation)
        return True, response, None

    async def update_investigation(
        self, investigation_id: str, user_id: str, update_data: InvestigationUpdate
    ) -> Tuple[bool, Optional[InvestigationResponse], Optional[str]]:
        """Update investigation"""
        # Get investigation and check ownership
        investigation = await self.investigation_repo.get_investigation_by_id(
            investigation_id
        )
        if not investigation:
            return False, None, "Investigation not found"

        if str(investigation["created_by"]) != user_id:
            return False, None, "Unauthorized"

        # Prepare update data
        update_dict = {}
        old_values = {}

        if update_data.title:
            update_dict["title"] = sanitize_input(update_data.title)
            old_values["title"] = investigation.get("title")

        if update_data.description:
            update_dict["description"] = sanitize_input(update_data.description)
            old_values["description"] = investigation.get("description")

        if update_data.priority:
            if not validate_priority(update_data.priority):
                return False, None, "Invalid priority level"
            update_dict["priority"] = update_data.priority
            old_values["priority"] = investigation.get("priority")

        if update_data.status:
            if not validate_investigation_status(update_data.status):
                return False, None, "Invalid status"
            update_dict["status"] = update_data.status
            old_values["status"] = investigation.get("status")

        if not update_dict:
            return False, None, "No fields to update"

        update_dict["updated_at"] = datetime.now(timezone.utc)

        # Update investigation
        success = await self.investigation_repo.update_investigation(
            investigation_id, update_dict
        )
        if not success:
            return False, None, "Failed to update investigation"

        # Create audit log
        changes = {f"old_{k}": v for k, v in old_values.items()}
        changes.update({f"new_{k}": v for k, v in update_dict.items() if k != "updated_at"})
        await self.audit_repo.create_log(
            investigation_id, user_id, "updated", changes
        )

        # Get updated investigation
        updated = await self.investigation_repo.get_investigation_by_id(
            investigation_id
        )
        response = InvestigationResponse(**updated)
        return True, response, None

    async def delete_investigation(
        self, investigation_id: str, user_id: str
    ) -> Tuple[bool, Optional[str]]:
        """Delete investigation"""
        # Get investigation and check ownership
        investigation = await self.investigation_repo.get_investigation_by_id(
            investigation_id
        )
        if not investigation:
            return False, "Investigation not found"

        if str(investigation["created_by"]) != user_id:
            return False, "Unauthorized"

        # Delete investigation
        success = await self.investigation_repo.delete_investigation(investigation_id)
        if not success:
            return False, "Failed to delete investigation"

        # Create audit log
        await self.audit_repo.create_log(investigation_id, user_id, "deleted")

        return True, None

    async def get_user_investigations(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 10,
        status: Optional[str] = None,
    ) -> Tuple[bool, Optional[List[InvestigationListResponse]], Optional[str]]:
        """Get user's investigations"""
        if status and not validate_investigation_status(status):
            return False, None, "Invalid status"

        try:
            investigations = await self.investigation_repo.get_investigations_by_user(
                user_id, skip, limit, status
            )
            responses = [
                InvestigationListResponse(
                    **{
                        **inv,
                        "seed_input_count": len(inv.get("seed_inputs", [])),
                    }
                )
                for inv in investigations
            ]
            return True, responses, None
        except Exception as e:
            return False, None, str(e)

    async def get_investigation_stats(
        self, user_id: str
    ) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """Get investigation statistics for user"""
        try:
            total = await self.investigation_repo.count_investigations_by_user(user_id)
            draft = await self.investigation_repo.count_investigations_by_user(
                user_id, "Draft"
            )
            active = await self.investigation_repo.count_investigations_by_user(
                user_id, "Active"
            )
            completed = await self.investigation_repo.count_investigations_by_user(
                user_id, "Completed"
            )
            archived = await self.investigation_repo.count_investigations_by_user(
                user_id, "Archived"
            )

            stats = {
                "total": total,
                "draft": draft,
                "active": active,
                "completed": completed,
                "archived": archived,
            }
            return True, stats, None
        except Exception as e:
            return False, None, str(e)

    async def add_seed_input(
        self, investigation_id: str, user_id: str, seed_input_type: str, value: str
    ) -> Tuple[bool, Optional[str]]:
        """Add seed input to investigation"""
        # Get investigation and check ownership
        investigation = await self.investigation_repo.get_investigation_by_id(
            investigation_id
        )
        if not investigation:
            return False, "Investigation not found"

        if str(investigation["created_by"]) != user_id:
            return False, "Unauthorized"

        # Validate seed input type
        if not validate_seed_input_type(seed_input_type):
            return False, f"Invalid seed input type: {seed_input_type}"

        # Add seed input
        seed_input = {
            "type": seed_input_type,
            "value": sanitize_input(value),
            "added_at": datetime.now(timezone.utc),
        }

        success = await self.investigation_repo.add_seed_input(
            investigation_id, seed_input
        )
        if not success:
            return False, "Failed to add seed input"

        # Create audit log
        await self.audit_repo.create_log(
            investigation_id,
            user_id,
            "seed_input_added",
            {"type": seed_input_type, "value": seed_input["value"]},
        )

        return True, None
