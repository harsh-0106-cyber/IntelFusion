"""Authentication Service"""
from typing import Optional, Dict, Tuple
from datetime import datetime, timezone
from bson import ObjectId
from motor.motor_asyncio import AsyncDatabase
from app.repositories.user_repo import UserRepository
from app.utils.security import hash_password, verify_password, create_access_token
from app.utils.validators import sanitize_input
from app.schemas.user import UserRegister, UserLogin, UserResponse


class AuthService:
    """Authentication service"""

    def __init__(self, db: AsyncDatabase):
        self.user_repo = UserRepository(db)

    async def register(
        self, user_data: UserRegister
    ) -> Tuple[bool, Optional[UserResponse], Optional[str]]:
        """Register a new user"""
        # Check if email already exists
        if await self.user_repo.email_exists(user_data.email):
            return False, None, "Email already registered"

        # Hash password and create user
        password_hash = hash_password(user_data.password)
        user_dict = {
            "name": sanitize_input(user_data.name),
            "email": user_data.email.lower(),
            "password_hash": password_hash,
            "role": "user",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

        try:
            user_id = await self.user_repo.create_user(user_dict)
            user_response = UserResponse(
                id=user_id,
                name=user_dict["name"],
                email=user_dict["email"],
                role=user_dict["role"],
                created_at=user_dict["created_at"],
                updated_at=user_dict["updated_at"],
            )
            return True, user_response, None
        except Exception as e:
            return False, None, str(e)

    async def login(
        self, login_data: UserLogin
    ) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """Login user and return JWT token"""
        # Get user by email
        user = await self.user_repo.get_by_email(login_data.email.lower())
        if not user:
            return False, None, "Invalid email or password"

        # Verify password
        if not verify_password(login_data.password, user["password_hash"]):
            return False, None, "Invalid email or password"

        # Create JWT token
        access_token = create_access_token(
            data={"sub": str(user["_id"]), "email": user["email"]}
        )

        response = {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": str(user["_id"]),
                "name": user["name"],
                "email": user["email"],
                "role": user["role"],
            },
        }
        return True, response, None

    async def get_current_user(self, user_id: str) -> Tuple[bool, Optional[UserResponse], Optional[str]]:
        """Get current user by ID"""
        user = await self.user_repo.get_user_by_id(user_id)
        if not user:
            return False, None, "User not found"

        user_response = UserResponse(
            id=str(user["_id"]),
            name=user["name"],
            email=user["email"],
            role=user["role"],
            created_at=user["created_at"],
            updated_at=user["updated_at"],
        )
        return True, user_response, None
