"""
Central model registry.

Every model must be imported here so that SQLAlchemy can resolve string-based
relationships and so Alembic autogenerate sees the full metadata.
"""

from app.core.database import Base  # noqa: F401

from app.models.alert_rule import AlertRule, AlertTrigger
from app.models.attendance import Attendance, Holiday, Shift, ShiftAssignment
from app.models.audit import ActivityLog, AuditLog, LoginHistory
from app.models.chat import Conversation, Message
from app.models.dataset import Dataset, DatasetColumn
from app.models.department import Department, Designation
from app.models.document import Document, DocumentCategory
from app.models.employee import Employee, EmployeeHistory
from app.models.forecast import ForecastDataPoint, ForecastScenario, WorkforceForecast
from app.models.intervention import InterventionAction, InterventionPlan
from app.models.leave import LeaveBalance, LeaveRequest, LeaveType
from app.models.notification import Notification, NotificationPreference
from app.models.payroll import (
    PayrollRun,
    Payslip,
    PayslipItem,
    SalaryComponent,
    SalaryStructure,
)
from app.models.performance import Feedback, Goal, PerformanceReview, ReviewCycle
from app.models.prediction import AttritionPrediction, ModelVersion, PredictionBatch
from app.models.recommendation import Recommendation, RecommendationFeedback
from app.models.report import GeneratedReport, ReportTemplate
from app.models.risk import RiskAlert, RiskFactor, RiskScore
from app.models.role import Permission, Role, role_permissions
from app.models.stability import StabilityMetric, StabilitySnapshot
from app.models.user import RefreshToken, User
from app.models.workflow import Task, TaskComment, Workflow, WorkflowStep

__all__ = [
    "Base",
    # auth & rbac
    "User",
    "RefreshToken",
    "Role",
    "Permission",
    "role_permissions",
    # org
    "Department",
    "Designation",
    "Employee",
    "EmployeeHistory",
    # attendance & leave
    "Shift",
    "ShiftAssignment",
    "Attendance",
    "Holiday",
    "LeaveType",
    "LeaveBalance",
    "LeaveRequest",
    # payroll
    "SalaryComponent",
    "SalaryStructure",
    "PayrollRun",
    "Payslip",
    "PayslipItem",
    # communication & documents
    "Notification",
    "NotificationPreference",
    "Conversation",
    "Message",
    "DocumentCategory",
    "Document",
    # ai / analytics
    "Dataset",
    "DatasetColumn",
    "ModelVersion",
    "PredictionBatch",
    "AttritionPrediction",
    "RiskScore",
    "RiskFactor",
    "RiskAlert",
    "WorkforceForecast",
    "ForecastDataPoint",
    "ForecastScenario",
    "InterventionPlan",
    "InterventionAction",
    "AlertRule",
    "AlertTrigger",
    # enterprise
    "ReportTemplate",
    "GeneratedReport",
    "AuditLog",
    "ActivityLog",
    "LoginHistory",
    "Workflow",
    "WorkflowStep",
    "Task",
    "TaskComment",
    "ReviewCycle",
    "PerformanceReview",
    "Goal",
    "Feedback",
    "Recommendation",
    "RecommendationFeedback",
    "StabilitySnapshot",
    "StabilityMetric",
]
