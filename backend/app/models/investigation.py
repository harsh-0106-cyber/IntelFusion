"""Investigation Model"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from bson import ObjectId


class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError(f"Invalid objectid {v}")
        return ObjectId(v)

    @classmethod
    def __get_pydantic_core_schema__(cls, _source_type, handler):
        from pydantic_core import core_schema
        return core_schema.no_info_after_validator_function(
            cls.validate,
            core_schema.union_schema([
                core_schema.is_instance_schema(ObjectId),
                core_schema.chain_schema([
                    core_schema.str_schema(),
                    core_schema.no_info_plain_validator_function(cls.validate),
                ]),
            ]),
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda instance: str(instance),
            ),
        )


class SeedInput(BaseModel):
    """Seed Input for Investigation"""
    type: str  # Name, Username, Company, Email, Phone, Keyword
    value: str
    added_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_schema_extra = {
            "example": {
                "type": "Email",
                "value": "john@example.com",
                "added_at": "2024-01-01T00:00:00",
            }
        }


class Investigation(BaseModel):
    """Investigation Database Model"""
    id: Optional[PyObjectId] = Field(alias="_id")
    title: str
    description: str
    status: str = "Draft"  # Draft, Active, Completed, Archived
    priority: str = "Medium"  # Low, Medium, High, Critical
    created_by: PyObjectId
    seed_inputs: List[SeedInput] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_schema_extra = {
            "example": {
                "_id": "507f1f77bcf86cd799439011",
                "title": "Investigation of Target XYZ",
                "description": "Gather public information about XYZ",
                "status": "Active",
                "priority": "High",
                "created_by": "507f1f77bcf86cd799439012",
                "seed_inputs": [
                    {
                        "type": "Email",
                        "value": "xyz@example.com",
                        "added_at": "2024-01-01T00:00:00",
                    }
                ],
                "created_at": "2024-01-01T00:00:00",
                "updated_at": "2024-01-01T00:00:00",
            }
        }


class AuditLog(BaseModel):
    """Audit Log Database Model"""
    id: Optional[PyObjectId] = Field(alias="_id")
    investigation_id: PyObjectId
    user_id: PyObjectId
    action: str  # created, updated, status_changed, deleted, archived
    changes: dict = {}
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_schema_extra = {
            "example": {
                "_id": "507f1f77bcf86cd799439013",
                "investigation_id": "507f1f77bcf86cd799439011",
                "user_id": "507f1f77bcf86cd799439012",
                "action": "status_changed",
                "changes": {"old_status": "Draft", "new_status": "Active"},
                "timestamp": "2024-01-01T00:00:00",
            }
        }
