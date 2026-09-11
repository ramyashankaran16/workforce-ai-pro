# WorkForce AI Pro - Backend Structure

Complete folder layout for all three phases. Files marked **[done]** are
implemented and tested; the rest are stubs carrying a docstring that lists the
planned surface, so the structure is fixed and each module can be filled in
without re-planning.

```
backend/
├── app/
│   ├── main.py                          [done] app factory, CORS, handlers, lifespan
│   │
│   ├── core/
│   │   ├── config.py                    [done] settings, DB URL via URL.create()
│   │   ├── database.py                  [done] engine, SessionLocal, Base, get_db
│   │   ├── security.py                  [done] bcrypt + JWT access/refresh
│   │   ├── dependencies.py              [done] get_current_user, RBAC guards
│   │   ├── permissions.py               [done] 60-permission catalogue + role map
│   │   ├── exceptions.py                [done] AppException hierarchy
│   │   ├── handlers.py                  [done] global error envelope
│   │   └── pagination.py                [done] PaginationParams, Page[T]
│   │
│   ├── models/                          [done] 24 modules, 59 tables
│   │   ├── enums.py  mixins.py  types.py
│   │   ├── user.py  role.py  department.py  employee.py
│   │   ├── attendance.py  leave.py  payroll.py
│   │   ├── notification.py  chat.py  document.py
│   │   ├── dataset.py  prediction.py  risk.py  forecast.py
│   │   ├── intervention.py  alert_rule.py
│   │   ├── report.py  audit.py  workflow.py  performance.py
│   │   ├── recommendation.py  stability.py
│   │   └── __init__.py                  registry - imports every model
│   │
│   ├── schemas/
│   │   ├── common.py  auth.py  user.py  role.py        [done]
│   │   └── employee.py ... stability.py  analytics.py  (21 stubs)
│   │
│   ├── api/v1/
│   │   ├── router.py                    [done] aggregator; stub includes commented
│   │   └── endpoints/
│   │       ├── auth.py  users.py  roles.py             [done]
│   │       ├── employees.py  departments.py  designations.py
│   │       ├── attendance.py  shifts.py  leaves.py  payroll.py
│   │       ├── notifications.py  chat.py  documents.py  dashboard.py
│   │       ├── datasets.py  predictions.py  risk.py  forecasting.py
│   │       ├── attrition_analytics.py  interventions.py
│   │       ├── alert_rules.py  monitoring.py
│   │       ├── reports.py  audit.py  workflows.py  performance.py
│   │       └── recommendations.py  search.py  stability.py
│   │
│   ├── services/
│   │   ├── auth_service.py              [done] login, lockout, refresh, passwords
│   │   └── 23 stubs mirroring the endpoint modules
│   │
│   ├── ml/
│   │   ├── preprocessing.py             encoders, scalers, cleaning
│   │   ├── feature_engineering.py       tenure, leave ratio, overtime ratio
│   │   ├── trainer.py                   train / evaluate / persist
│   │   ├── predictor.py                 load artifact, single + batch scoring
│   │   ├── explainer.py                 per-employee feature contributions
│   │   ├── forecaster.py                headcount and attrition projection
│   │   └── registry.py                  model version bookkeeping
│   │
│   ├── websockets/
│   │   ├── manager.py                   ConnectionManager (in-process)
│   │   ├── chat_ws.py                   one-to-one chat socket
│   │   └── monitoring_ws.py             live alert push
│   │
│   ├── middleware/
│   │   ├── audit_middleware.py          auto-log mutating requests
│   │   ├── rate_limit.py                throttle /auth against credential stuffing
│   │   └── request_logger.py            structured request logs
│   │
│   ├── tasks/
│   │   ├── scheduler.py                 APScheduler setup
│   │   ├── attendance_jobs.py           nightly absent marking, forgotten check-outs
│   │   ├── daily_risk_scan.py           batch scoring + alert rule evaluation
│   │   ├── report_jobs.py               scheduled report generation
│   │   └── document_jobs.py             expiry notifications
│   │
│   └── utils/
│       ├── date_utils.py                [done] utcnow, working-day helpers
│       ├── file_handler.py              upload validation, storage paths
│       ├── excel_export.py  pdf_export.py
│       ├── validators.py                phone, PAN, IFSC
│       └── code_generator.py            employee codes, payslip numbers
│
├── alembic/
│   ├── env.py                           [done] reads URL from app settings
│   ├── script.py.mako                   [done]
│   └── versions/                        (empty - first revision pending)
│
├── scripts/
│   ├── create_tables.py                 [done] build schema, --create-db, --drop
│   ├── seed_data.py                     [done] roles, permissions, admin, masters
│   ├── check_db.py                      [done] connection diagnostic
│   ├── verify_login.py                  [done] login failure diagnosis
│   └── reset_password.py                [done] direct password reset
│
├── tests/
│   ├── conftest.py                      [done] SQLite fixtures, per-role clients
│   ├── test_auth.py                     [done] 13 tests
│   ├── test_rbac.py                     [done] 15 tests
│   └── 12 stubs (skipped until their module exists)
│
├── ml_models/  datasets/  uploads/  logs/     runtime directories
├── Dockerfile  docker-compose.yml  .dockerignore
├── alembic.ini  pytest.ini  requirements.txt
├── .env.example  .gitignore
├── README.md  STRUCTURE.md  DATABASE_SCHEMA.md
```

## Layering

```
HTTP request
   -> api/v1/endpoints/     routing, RBAC guard, request/response schemas
      -> services/          business rules, transactions
         -> models/         ORM, constraints
   ml/ is called only by services, never by endpoints
```

Endpoints never touch the ORM directly beyond simple reads; anything with a
rule in it belongs in a service. That keeps the same logic reachable from a
scheduled job as from an HTTP route.

## Build order

| Step | Modules | Status |
|---|---|---|
| 1 | Database models, 59 tables | done |
| 2 | Security, RBAC, auth, users, roles | done |
| 3 | Employee, Department, Designation | next |
| 4 | Attendance, Shift, Leave | |
| 5 | Payroll | |
| 6 | Notifications, Chat, Documents, Dashboard | |
| 7 | Dataset + ML training pipeline | |
| 8 | Predictions, Risk, Forecast, Interventions, Alerts | |
| 9 | Reports, Audit, Workflow, Performance, Search, Stability | |

## Known limitations to state in the submission

**WebSocket state is in-process.** `app/websockets/manager.py` holds connections
in memory, so a worker holding a socket cannot be reached by another worker
handling the triggering request. Runs single-worker; scaling out needs Redis
pub/sub.

**APScheduler runs per instance.** Two app instances means every job fires
twice. Needs a dedicated scheduler process or a distributed lock.

**No Alembic revision yet.** Schema is currently built with `create_all`, which
is fine for development but cannot ship an incremental change to a running
system. First revision should be generated before any schema change.

**Tests run on SQLite.** Fast and dependency-free, but blind to PostgreSQL
specifics: JSONB operators, `ILIKE` collation behaviour, transactional DDL.
Worth a separate CI run against PostgreSQL.
