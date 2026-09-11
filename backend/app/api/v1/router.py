"""
Aggregates every v1 endpoint router.

Implemented modules are included below. Stubs are listed but commented out --
uncomment each as its routes are built so Swagger only advertises working
endpoints.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    departments,
    designations,
    alert_rules,
    attendance,
    attrition_analytics,
    audit,
    chat,
    dashboard,
    datasets,
    documents,
    employees,
    forecasting,
    interventions,
    leaves,
    monitoring,
    notifications,
    payroll,
    performance,
    predictions,
    recommendations,
    reports,
    risk,
    roles,
    search,
    stability,
    shifts,
    users,
    workflows,
)

api_router = APIRouter()

# ---- implemented -------------------------------------------------------
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(roles.router)
api_router.include_router(departments.router)
api_router.include_router(designations.router)
api_router.include_router(employees.router)
api_router.include_router(shifts.router)
api_router.include_router(attendance.router)
api_router.include_router(leaves.router)
api_router.include_router(payroll.router)
api_router.include_router(datasets.router)
api_router.include_router(predictions.router)
api_router.include_router(risk.router)
api_router.include_router(alert_rules.router)
api_router.include_router(forecasting.router)
api_router.include_router(interventions.router)
api_router.include_router(attrition_analytics.router)
api_router.include_router(notifications.router)
api_router.include_router(chat.router)
api_router.include_router(documents.router)
api_router.include_router(dashboard.router)
api_router.include_router(monitoring.router)
api_router.include_router(reports.router)
api_router.include_router(audit.router)
api_router.include_router(workflows.router)
api_router.include_router(performance.router)
api_router.include_router(recommendations.router)
api_router.include_router(search.router)
api_router.include_router(stability.router)
api_router.include_router(datasets.router)
api_router.include_router(predictions.router)

# api_router.include_router(notifications.router)
# api_router.include_router(chat.router)
# api_router.include_router(documents.router)
# api_router.include_router(dashboard.router)

# ---- Phase 2: AI & intelligence ----------------------------------------
