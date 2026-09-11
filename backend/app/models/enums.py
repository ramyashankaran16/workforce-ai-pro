"""
Central enum definitions for WorkForce AI Pro.

All enums subclass `str` so FastAPI/Pydantic serialise them as plain strings
and SQLAlchemy stores readable values in MySQL.
"""

import enum

from sqlalchemy import Enum as SAEnum


def enum_col(enum_cls, length: int = 40):
    """
    Build a portable Enum column.

    native_enum=False stores values as VARCHAR instead of a MySQL ENUM, which
    makes adding new members painless during migrations.
    """
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda x: [e.value for e in x],
    )


# ---------------------------------------------------------------- Auth / RBAC
class UserRoleEnum(str, enum.Enum):
    ADMIN = "admin"
    HR = "hr"
    MANAGER = "manager"
    EMPLOYEE = "employee"


class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING = "pending"


# ------------------------------------------------------------------- Employee
class Gender(str, enum.Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"
    UNDISCLOSED = "undisclosed"


class MaritalStatus(str, enum.Enum):
    SINGLE = "single"
    MARRIED = "married"
    DIVORCED = "divorced"
    WIDOWED = "widowed"


class EmploymentType(str, enum.Enum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERN = "intern"
    CONSULTANT = "consultant"


class EmployeeStatus(str, enum.Enum):
    ACTIVE = "active"
    ON_LEAVE = "on_leave"
    NOTICE_PERIOD = "notice_period"
    RESIGNED = "resigned"
    TERMINATED = "terminated"
    RETIRED = "retired"


class WorkMode(str, enum.Enum):
    ONSITE = "onsite"
    REMOTE = "remote"
    HYBRID = "hybrid"


class EmployeeEventType(str, enum.Enum):
    JOINED = "joined"
    PROMOTION = "promotion"
    TRANSFER = "transfer"
    SALARY_REVISION = "salary_revision"
    ROLE_CHANGE = "role_change"
    MANAGER_CHANGE = "manager_change"
    STATUS_CHANGE = "status_change"
    EXIT = "exit"


# ----------------------------------------------------------------- Attendance
class AttendanceStatus(str, enum.Enum):
    PRESENT = "present"
    ABSENT = "absent"
    HALF_DAY = "half_day"
    LATE = "late"
    ON_LEAVE = "on_leave"
    HOLIDAY = "holiday"
    WEEKEND = "weekend"
    WORK_FROM_HOME = "work_from_home"


class ShiftType(str, enum.Enum):
    GENERAL = "general"
    MORNING = "morning"
    EVENING = "evening"
    NIGHT = "night"
    FLEXIBLE = "flexible"


class RegularizationStatus(str, enum.Enum):
    NOT_REQUESTED = "not_requested"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


# ---------------------------------------------------------------------- Leave
class LeaveStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class LeaveDuration(str, enum.Enum):
    FULL_DAY = "full_day"
    FIRST_HALF = "first_half"
    SECOND_HALF = "second_half"


# -------------------------------------------------------------------- Payroll
class PayrollStatus(str, enum.Enum):
    DRAFT = "draft"
    PROCESSING = "processing"
    PROCESSED = "processed"
    APPROVED = "approved"
    PAID = "paid"
    FAILED = "failed"


class PayComponentType(str, enum.Enum):
    EARNING = "earning"
    DEDUCTION = "deduction"


class PayFrequency(str, enum.Enum):
    MONTHLY = "monthly"
    BIWEEKLY = "biweekly"
    WEEKLY = "weekly"


# -------------------------------------------------------------- Notifications
class NotificationType(str, enum.Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    ALERT = "alert"


class NotificationCategory(str, enum.Enum):
    SYSTEM = "system"
    ATTENDANCE = "attendance"
    LEAVE = "leave"
    PAYROLL = "payroll"
    CHAT = "chat"
    DOCUMENT = "document"
    ATTRITION_RISK = "attrition_risk"
    TASK = "task"
    PERFORMANCE = "performance"
    APPROVAL = "approval"


class NotificationChannel(str, enum.Enum):
    IN_APP = "in_app"
    EMAIL = "email"
    SMS = "sms"


class Priority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ----------------------------------------------------------------------- Chat
class MessageType(str, enum.Enum):
    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    SYSTEM = "system"


# ------------------------------------------------------------------ Documents
class DocumentStatus(str, enum.Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"
    EXPIRED = "expired"


class DocumentVisibility(str, enum.Enum):
    PRIVATE = "private"
    MANAGER = "manager"
    HR_ONLY = "hr_only"
    PUBLIC = "public"


# --------------------------------------------------------------- ML / Dataset
class DatasetStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    VALIDATING = "validating"
    VALIDATED = "validated"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class ColumnDataType(str, enum.Enum):
    NUMERIC = "numeric"
    CATEGORICAL = "categorical"
    BOOLEAN = "boolean"
    DATETIME = "datetime"
    TEXT = "text"


class ModelStatus(str, enum.Enum):
    QUEUED = "queued"
    TRAINING = "training"
    TRAINED = "trained"
    DEPLOYED = "deployed"
    ARCHIVED = "archived"
    FAILED = "failed"


class ModelAlgorithm(str, enum.Enum):
    LOGISTIC_REGRESSION = "logistic_regression"
    RANDOM_FOREST = "random_forest"
    GRADIENT_BOOSTING = "gradient_boosting"
    DECISION_TREE = "decision_tree"
    SVM = "svm"
    KNN = "knn"
    NAIVE_BAYES = "naive_bayes"


class PredictionSource(str, enum.Enum):
    MANUAL = "manual"
    BATCH = "batch"
    SCHEDULED = "scheduled"
    API = "api"


# ----------------------------------------------------------------------- Risk
class RiskLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskTrend(str, enum.Enum):
    IMPROVING = "improving"
    STABLE = "stable"
    WORSENING = "worsening"


class AlertStatus(str, enum.Enum):
    NEW = "new"
    ACKNOWLEDGED = "acknowledged"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


# ------------------------------------------------------------------ Forecasts
class ForecastType(str, enum.Enum):
    HEADCOUNT = "headcount"
    ATTRITION_RATE = "attrition_rate"
    HIRING_NEED = "hiring_need"
    COST = "cost"


class ForecastGranularity(str, enum.Enum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


# -------------------------------------------------------------- Interventions
class InterventionType(str, enum.Enum):
    SALARY_REVISION = "salary_revision"
    PROMOTION = "promotion"
    TRAINING = "training"
    ROLE_CHANGE = "role_change"
    COUNSELLING = "counselling"
    WORKLOAD_ADJUSTMENT = "workload_adjustment"
    RECOGNITION = "recognition"
    MENTORSHIP = "mentorship"
    FLEXIBLE_WORK = "flexible_work"
    OTHER = "other"


class InterventionStatus(str, enum.Enum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class InterventionOutcome(str, enum.Enum):
    PENDING = "pending"
    SUCCESSFUL = "successful"
    PARTIAL = "partial"
    UNSUCCESSFUL = "unsuccessful"


# ---------------------------------------------------------------- Alert rules
class RuleOperator(str, enum.Enum):
    GREATER_THAN = "gt"
    GREATER_OR_EQUAL = "gte"
    LESS_THAN = "lt"
    LESS_OR_EQUAL = "lte"
    EQUAL = "eq"
    NOT_EQUAL = "neq"
    BETWEEN = "between"


class RuleTargetMetric(str, enum.Enum):
    ATTRITION_PROBABILITY = "attrition_probability"
    RISK_SCORE = "risk_score"
    ABSENCE_RATE = "absence_rate"
    OVERTIME_HOURS = "overtime_hours"
    LEAVE_BALANCE = "leave_balance"
    PERFORMANCE_RATING = "performance_rating"
    TENURE_MONTHS = "tenure_months"
    DEPARTMENT_ATTRITION = "department_attrition"


# -------------------------------------------------------------------- Reports
class ReportFormat(str, enum.Enum):
    PDF = "pdf"
    EXCEL = "excel"
    CSV = "csv"
    JSON = "json"


class ReportStatus(str, enum.Enum):
    QUEUED = "queued"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class ReportCategory(str, enum.Enum):
    ATTENDANCE = "attendance"
    LEAVE = "leave"
    PAYROLL = "payroll"
    ATTRITION = "attrition"
    PERFORMANCE = "performance"
    HEADCOUNT = "headcount"
    AUDIT = "audit"
    CUSTOM = "custom"


# ---------------------------------------------------------------------- Audit
class AuditAction(str, enum.Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    LOGIN = "login"
    LOGOUT = "logout"
    LOGIN_FAILED = "login_failed"
    EXPORT = "export"
    IMPORT = "import"
    APPROVE = "approve"
    REJECT = "reject"
    VIEW = "view"
    DOWNLOAD = "download"


# ------------------------------------------------------------------ Workflows
class WorkflowStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class TaskStatus(str, enum.Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------- Performance
class ReviewCycleStatus(str, enum.Enum):
    PLANNED = "planned"
    OPEN = "open"
    CLOSED = "closed"
    ARCHIVED = "archived"


class ReviewStatus(str, enum.Enum):
    DRAFT = "draft"
    SELF_REVIEW = "self_review"
    MANAGER_REVIEW = "manager_review"
    HR_REVIEW = "hr_review"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class GoalStatus(str, enum.Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    ACHIEVED = "achieved"
    MISSED = "missed"
    CANCELLED = "cancelled"


# ------------------------------------------------------------ Recommendations
class RecommendationCategory(str, enum.Enum):
    RETENTION = "retention"
    HIRING = "hiring"
    TRAINING = "training"
    COMPENSATION = "compensation"
    ENGAGEMENT = "engagement"
    WORKLOAD = "workload"
    POLICY = "policy"


class RecommendationStatus(str, enum.Enum):
    NEW = "new"
    VIEWED = "viewed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    IMPLEMENTED = "implemented"


class TargetScope(str, enum.Enum):
    ORGANISATION = "organisation"
    DEPARTMENT = "department"
    TEAM = "team"
    EMPLOYEE = "employee"


# ------------------------------------------------------------------ Stability
class StabilityGrade(str, enum.Enum):
    EXCELLENT = "excellent"
    GOOD = "good"
    MODERATE = "moderate"
    POOR = "poor"
    CRITICAL = "critical"
