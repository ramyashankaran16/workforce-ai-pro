"""
Permission catalogue and role -> permission mapping.

Codes follow "<module>:<action>". The seed script writes these into the
permissions table and links them to roles.
"""

from typing import Dict, List, Tuple

# (code, human name, module)
PERMISSION_CATALOGUE: List[Tuple[str, str, str]] = [
    # users & roles
    ("user:create", "Create users", "users"),
    ("user:read", "View users", "users"),
    ("user:update", "Update users", "users"),
    ("user:delete", "Deactivate users", "users"),
    ("user:reset_password", "Reset another user's password", "users"),
    ("role:read", "View roles and permissions", "roles"),
    ("role:manage", "Create and modify roles", "roles"),
    # employees
    ("employee:create", "Create employees", "employees"),
    ("employee:read", "View employee records", "employees"),
    ("employee:read_all", "View every employee", "employees"),
    ("employee:update", "Update employee records", "employees"),
    ("employee:delete", "Deactivate employees", "employees"),
    # org structure
    ("department:read", "View departments", "departments"),
    ("department:manage", "Create and modify departments", "departments"),
    # attendance
    ("attendance:mark", "Mark own attendance", "attendance"),
    ("attendance:read", "View own attendance", "attendance"),
    ("attendance:read_team", "View team attendance", "attendance"),
    ("attendance:read_all", "View all attendance", "attendance"),
    ("attendance:manage", "Edit and regularise attendance", "attendance"),
    ("shift:manage", "Create and assign shifts", "attendance"),
    # leave
    ("leave:apply", "Apply for leave", "leave"),
    ("leave:read", "View own leave", "leave"),
    ("leave:read_team", "View team leave", "leave"),
    ("leave:read_all", "View all leave", "leave"),
    ("leave:approve", "Approve or reject leave", "leave"),
    ("leave:manage", "Configure leave types and balances", "leave"),
    # payroll
    ("payroll:read_own", "View own payslips", "payroll"),
    ("payroll:read_all", "View all payroll data", "payroll"),
    ("payroll:process", "Run payroll", "payroll"),
    ("payroll:manage", "Configure salary structures", "payroll"),
    # documents
    ("document:upload", "Upload documents", "documents"),
    ("document:read_own", "View own documents", "documents"),
    ("document:read_all", "View all documents", "documents"),
    ("document:verify", "Verify or reject documents", "documents"),
    # analytics & ai
    ("dashboard:read", "View dashboards", "analytics"),
    ("analytics:read_team", "View team analytics", "analytics"),
    ("analytics:read_all", "View organisation analytics", "analytics"),
    ("dataset:manage", "Upload and manage datasets", "ai"),
    ("model:train", "Train prediction models", "ai"),
    ("model:deploy", "Deploy prediction models", "ai"),
    ("prediction:run", "Run attrition predictions", "ai"),
    ("prediction:read", "View prediction results", "ai"),
    ("risk:read_team", "View team risk scores", "ai"),
    ("risk:read_all", "View all risk scores", "ai"),
    ("risk:manage", "Acknowledge and resolve risk alerts", "ai"),
    ("forecast:manage", "Create workforce forecasts", "ai"),
    ("intervention:manage", "Create and run interventions", "ai"),
    ("alert_rule:manage", "Configure alert rules", "ai"),
    ("recommendation:read", "View AI recommendations", "ai"),
    # enterprise
    ("report:generate", "Generate reports", "reports"),
    ("report:manage", "Manage report templates", "reports"),
    ("audit:read", "View audit logs", "audit"),
    ("task:read", "View assigned tasks", "workflow"),
    ("task:manage", "Create and assign tasks", "workflow"),
    ("workflow:manage", "Configure workflows", "workflow"),
    ("performance:read_own", "View own reviews", "performance"),
    ("performance:read_team", "View team reviews", "performance"),
    ("performance:manage", "Run review cycles", "performance"),
    ("stability:read", "View workforce stability index", "analytics"),
    ("system:manage", "Manage system settings", "system"),
]

ALL_PERMISSION_CODES = [code for code, _, _ in PERMISSION_CATALOGUE]

# Role definitions: name -> (display name, hierarchy level, description)
ROLE_DEFINITIONS: Dict[str, Tuple[str, int, str]] = {
    "admin": ("Administrator", 1, "Full access to every module and setting."),
    "hr": ("HR Manager", 2, "Manages people operations, payroll and AI insights."),
    "manager": ("Manager", 3, "Manages their own reporting team."),
    "employee": ("Employee", 4, "Self-service access to their own records."),
}

# admin gets everything, so it is filled in by the seed script
ROLE_PERMISSIONS: Dict[str, List[str]] = {
    "admin": ALL_PERMISSION_CODES,
    "hr": [
        "user:create", "user:read", "user:update", "user:reset_password",
        "role:read",
        "employee:create", "employee:read", "employee:read_all",
        "employee:update", "employee:delete",
        "department:read", "department:manage",
        "attendance:mark", "attendance:read", "attendance:read_all",
        "attendance:manage", "shift:manage",
        "leave:apply", "leave:read", "leave:read_all", "leave:approve", "leave:manage",
        "payroll:read_own", "payroll:read_all", "payroll:process", "payroll:manage",
        "document:upload", "document:read_own", "document:read_all", "document:verify",
        "dashboard:read", "analytics:read_all",
        "dataset:manage", "model:train", "model:deploy",
        "prediction:run", "prediction:read",
        "risk:read_all", "risk:manage",
        "forecast:manage", "intervention:manage", "alert_rule:manage",
        "recommendation:read",
        "report:generate", "report:manage", "audit:read",
        "task:read", "task:manage", "workflow:manage",
        "performance:read_own", "performance:read_team", "performance:manage",
        "stability:read",
    ],
    "manager": [
        "user:read",
        "employee:read",
        "department:read",
        "attendance:mark", "attendance:read", "attendance:read_team",
        "leave:apply", "leave:read", "leave:read_team", "leave:approve",
        "payroll:read_own",
        "document:upload", "document:read_own",
        "dashboard:read", "analytics:read_team",
        "prediction:read", "risk:read_team", "intervention:manage",
        "recommendation:read",
        "report:generate",
        "task:read", "task:manage",
        "performance:read_own", "performance:read_team",
    ],
    "employee": [
        "attendance:mark", "attendance:read",
        "leave:apply", "leave:read",
        "payroll:read_own",
        "document:upload", "document:read_own",
        "dashboard:read",
        "task:read",
        "performance:read_own",
    ],
}
