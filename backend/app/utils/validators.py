"""Input Validators"""
import re
from typing import List


VALID_SEED_INPUT_TYPES = ["Name", "Username", "Company", "Email", "Phone", "Keyword"]
VALID_INVESTIGATION_STATUSES = ["Draft", "Active", "Completed", "Archived"]
VALID_PRIORITIES = ["Low", "Medium", "High", "Critical"]


def validate_seed_input_type(input_type: str) -> bool:
    """Validate seed input type"""
    return input_type in VALID_SEED_INPUT_TYPES


def validate_investigation_status(status: str) -> bool:
    """Validate investigation status"""
    return status in VALID_INVESTIGATION_STATUSES


def validate_priority(priority: str) -> bool:
    """Validate priority level"""
    return priority in VALID_PRIORITIES


def validate_email(email: str) -> bool:
    """Validate email format"""
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email) is not None


def validate_phone(phone: str) -> bool:
    """Validate phone number format (basic)"""
    pattern = r"^[+]?[(]?[0-9]{1,4}[)]?[-\s\.]?[(]?[0-9]{1,4}[)]?[-\s\.]?[0-9]{1,9}$"
    return re.match(pattern, phone) is not None


def sanitize_input(value: str) -> str:
    """Basic input sanitization"""
    # Remove leading/trailing whitespace
    value = value.strip()
    # Remove potentially dangerous characters
    dangerous_chars = ["<", ">", "&", "'", '"']
    for char in dangerous_chars:
        value = value.replace(char, "")
    return value
