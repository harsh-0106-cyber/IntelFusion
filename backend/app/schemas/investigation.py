"""Investigation Schemas"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class SeedInputCreate(BaseModel):
    """Seed Input Creation Schema"""
    type: str = Field(..., description="Type: Name, Username, Company, Email, Phone, Keyword")
    value: str = Field(..., min_length=1, max_length=500)

    class Config:
        json_schema_extra = {
            "example": {
                "type": "Email",
                "value": "john@example.com",
            }
        }


class SeedInputResponse(BaseModel):
    """Seed Input Response Schema"""
    type: str
    value: str
    added_at: datetime


class InvestigationCreate(BaseModel):
    """Investigation Creation Schema"""
    title: str = Field(..., min_length=3, max_length=200)
    description: str = Field(..., min_length=10, max_length=2000)
    priority: str = Field(default="Medium", description="Low, Medium, High, Critical")
    seed_inputs: Optional[List[SeedInputCreate]] = None

    class Config:
        json_schema_extra = {
            "example": {
                "title": "Investigation of Target XYZ",
                "description": "Gather public information about XYZ company and its employees",
                "priority": "High",
                "seed_inputs": [
                    {"type": "Email", "value": "xyz@example.com"},
                    {"type": "Company", "value": "XYZ Corp"},
                ],
            }
        }


class InvestigationUpdate(BaseModel):
    """Investigation Update Schema"""
    title: Optional[str] = Field(None, min_length=3, max_length=200)
    description: Optional[str] = Field(None, min_length=10, max_length=2000)
    priority: Optional[str] = None
    status: Optional[str] = Field(None, description="Draft, Active, Completed, Archived")

    class Config:
        json_schema_extra = {
            "example": {
                "title": "Updated Investigation Title",
                "description": "Updated description",
                "priority": "Critical",
                "status": "Active",
            }
        }


class InvestigationResponse(BaseModel):
    """Investigation Response Schema"""
    id: str = Field(alias="_id")
    title: str
    description: str
    status: str
    priority: str
    created_by: str
    seed_inputs: List[SeedInputResponse]
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True
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


class InvestigationListResponse(BaseModel):
    """Investigation List Response Schema"""
    id: str = Field(alias="_id")
    title: str
    status: str
    priority: str
    created_by: str
    created_at: datetime
    seed_input_count: int = 0

    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "_id": "507f1f77bcf86cd799439011",
                "title": "Investigation of Target XYZ",
                "status": "Active",
                "priority": "High",
                "created_by": "507f1f77bcf86cd799439012",
                "created_at": "2024-01-01T00:00:00",
                "seed_input_count": 1,
            }
        }


class AuditLogResponse(BaseModel):
    """Audit Log Response Schema"""
    id: str = Field(alias="_id")
    investigation_id: str
    user_id: str
    action: str
    changes: dict
    timestamp: datetime

    class Config:
        populate_by_name = True
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
