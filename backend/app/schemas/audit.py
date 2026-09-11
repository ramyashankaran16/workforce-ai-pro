"""Audit schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from app.models.enums import AuditAction
from app.schemas.common import ORMBase


class AuditLogRead(ORMBase):
    id: int
    user_id: Optional[int] = None
    user_email: Optional[str] = None
    user_role: Optional[str] = None
    action: AuditAction
    entity_type: str
    entity_id: Optional[int] = None
    description: Optional[str] = None
    endpoint: Optional[str] = None
    http_method: Optional[str] = None
    status_code: Optional[int] = None
    duration_ms: Optional[float] = None
    ip_address: Optional[str] = None
    is_successful: bool
    error_message: Optional[str] = None
    created_at: datetime


class AuditLogDetail(AuditLogRead):
    old_values: Optional[Dict[str, Any]] = None
    new_values: Optional[Dict[str, Any]] = None
    changed_fields: Optional[Dict[str, Any]] = None


class ActivityLogRead(ORMBase):
    id: int
    activity_type: str
    title: str
    description: Optional[str] = None
    module: Optional[str] = None
    reference_type: Optional[str] = None
    reference_id: Optional[int] = None
    created_at: datetime


class LoginHistoryRead(ORMBase):
    id: int
    user_id: Optional[int] = None
    email_attempted: str
    is_successful: bool
    failure_reason: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    logged_in_at: datetime


class AuditSummary(BaseModel):
    window_days: int
    total_entries: int
    failed_operations: int
    failed_logins: int
    by_action: Dict[str, int] = {}
    by_entity: Dict[str, int] = {}
    most_active_users: List[Dict[str, Any]] = []


class SuspiciousLogin(BaseModel):
    email: str
    failed_attempts: int
    last_attempt: datetime
    window_hours: int
