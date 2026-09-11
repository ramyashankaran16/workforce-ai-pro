# WorkForce AI Pro - Backend (Step 1: Database Layer)

HR Attrition Prediction & Workforce Intelligence Platform.
This package contains the complete SQLAlchemy model layer - **59 tables** covering
all three phases of the assignment.

## What's included

```
backend/
├── app/
│   ├── core/
│   │   ├── config.py          # Settings, PostgreSQL URL built with URL.create()
│   │   └── database.py        # Engine, SessionLocal, Base, get_db()
│   └── models/
│       ├── enums.py           # 45+ shared enums
│       ├── mixins.py          # TimestampMixin, SoftDeleteMixin
│       ├── types.py           # JSONType (JSONB on PostgreSQL)
│       ├── __init__.py        # Registry - imports every model
│       └── <22 model modules>
├── scripts/
│   ├── create_tables.py       # Builds the schema in PostgreSQL
│   └── check_db.py            # Connection diagnostic
├── DATABASE_SCHEMA.md         # Auto-generated table reference
├── requirements.txt
└── .env.example
```

## Setup (Windows / PowerShell)

```powershell
cd backend

python -m venv venv
.\venv\Scripts\Activate.ps1
# if activation is blocked:
# Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

pip install -r requirements.txt
```

Make sure PostgreSQL is running, then create the database. Either use pgAdmin 4
(right-click **Databases** -> Create -> Database, name it `workforce_ai_pro`), or
let the script do it:

```powershell
copy .env.example .env
# edit .env with your postgres password
python -m scripts.check_db          # verify credentials
python -m scripts.create_tables --create-db
```

You should see all 59 tables listed. To wipe and rebuild:

```powershell
python -m scripts.create_tables --drop
```

Refresh the `workforce_ai_pro` node in pgAdmin 4 and open
**Schemas -> public -> Tables** to browse them.

## Design notes

**Database** - PostgreSQL 14+ via `psycopg2`. pgAdmin 4 is the GUI client.

**Passwords** - `bcrypt` is used directly rather than through `passlib`, which
avoids the version-detection error the two libraries produce together.

**PostgreSQL connection** - the URL is assembled with SQLAlchemy's `URL.create()`, so
special characters (`@ # / % :`) in the password are escaped automatically.

**Enums** - stored as `VARCHAR` with a CHECK constraint (`native_enum=False`)
rather than native PostgreSQL `ENUM` types. Adding a new member later is a code
change instead of an `ALTER TYPE`, which PostgreSQL cannot run inside a
transaction.

**Circular foreign key** - `departments.head_employee_id` references `employees`
while `employees.department_id` references `departments`. The department side uses
`use_alter=True` plus `post_update=True`, so the constraint is added after both
tables exist.

**JSON columns** - `app/models/types.py` defines `JSONType`, which renders as
`JSONB` on PostgreSQL (indexable, faster containment queries) and plain `JSON`
elsewhere.

**Soft deletes** - master data (users, employees, departments, documents,
workflows, tasks) carries `is_deleted` / `deleted_at`. Transactional rows are
never soft-deleted, and audit tables are append-only.

**Denormalised risk fields** - `employees.current_risk_score` and
`current_risk_level` are refreshed by the scheduled scoring job so the dashboard
can filter high-risk staff without joining `risk_scores` on every request.

## Table map

| Phase | Area | Tables |
|---|---|---|
| 1 | Auth & RBAC | users, refresh_tokens, roles, permissions, role_permissions |
| 1 | Organisation | departments, designations, employees, employee_history |
| 1 | Attendance | shifts, shift_assignments, attendances, holidays |
| 1 | Leave | leave_types, leave_balances, leave_requests |
| 1 | Payroll | salary_components, salary_structures, payroll_runs, payslips, payslip_items |
| 1 | Comms | notifications, notification_preferences, conversations, messages |
| 1 | Documents | document_categories, documents |
| 2 | Datasets | datasets, dataset_columns |
| 2 | Prediction | model_versions, prediction_batches, attrition_predictions |
| 2 | Risk | risk_scores, risk_factors, risk_alerts |
| 2 | Forecasting | workforce_forecasts, forecast_data_points, forecast_scenarios |
| 2 | Intervention | intervention_plans, intervention_actions |
| 2 | Alert engine | alert_rules, alert_triggers |
| 3 | Reports | report_templates, generated_reports |
| 3 | Audit | audit_logs, activity_logs, login_history |
| 3 | Workflow | workflows, workflow_steps, tasks, task_comments |
| 3 | Performance | review_cycles, performance_reviews, goals, feedbacks |
| 3 | Recommendations | recommendations, recommendation_feedbacks |
| 3 | Stability | stability_snapshots, stability_metrics |

Full column-level reference: **DATABASE_SCHEMA.md**

## Next step

Step 2 - security (`bcrypt` + JWT), RBAC dependencies, seed script for roles,
permissions and the default admin, then the auth endpoints.

---

# Step 2: Authentication, RBAC & User Management

## New files

```
app/
├── core/
│   ├── security.py        # bcrypt hashing + JWT access/refresh tokens
│   ├── dependencies.py    # get_current_user, RequirePermissions, RequireRoles
│   ├── permissions.py     # 60-permission catalogue + role mapping
│   ├── exceptions.py      # AppException hierarchy with stable error codes
│   ├── handlers.py        # global handlers -> one error envelope
│   └── pagination.py      # PaginationParams + Page[T]
├── schemas/
│   ├── common.py  auth.py  user.py  role.py
├── services/
│   └── auth_service.py    # login, lockout, refresh, password flows
├── api/v1/
│   ├── router.py
│   └── endpoints/  auth.py  users.py  roles.py
├── utils/date_utils.py
└── main.py                # app factory, CORS, handlers, lifespan
scripts/seed_data.py
tests/  conftest.py  test_auth.py  test_rbac.py
```

## Seed and run

```powershell
python -m scripts.seed_data
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs and sign in:

```json
POST /api/v1/auth/login
{ "email": "admin@workforce.ai", "password": "Admin@123" }
```

Copy `access_token` into the **Authorize** button.

## Endpoints

| Method | Path | Guard |
|---|---|---|
| POST | `/auth/login` | public |
| POST | `/auth/token` | public (OAuth2 form, for Swagger) |
| POST | `/auth/refresh` | public (valid refresh token) |
| POST | `/auth/logout` | authenticated |
| GET | `/auth/me` | authenticated |
| GET | `/auth/permissions` | authenticated |
| POST | `/auth/change-password` | authenticated |
| POST | `/auth/register` | `user:create` |
| POST | `/auth/reset-password` | `user:reset_password` |
| GET | `/users` | `user:read` |
| GET | `/users/{id}` | `user:read` |
| PATCH | `/users/{id}` | `user:update` |
| DELETE | `/users/{id}` | `user:delete` |
| POST | `/users/{id}/activate` | `user:update` |
| GET | `/roles` | `role:read` |
| GET | `/roles/permissions` | `role:read` |
| GET | `/roles/{id}` | `role:read` |
| POST | `/roles` | `role:manage` |
| PATCH | `/roles/{id}` | `role:manage` |
| PUT | `/roles/{id}/permissions` | `role:manage` |
| DELETE | `/roles/{id}` | `role:manage` |

## Permission counts by role

| Role | Level | Permissions |
|---|---|---|
| admin | 1 | 60 (all) |
| hr | 2 | 53 |
| manager | 3 | 24 |
| employee | 4 | 10 |

## Security decisions

**Account lockout** - 5 consecutive failures locks the account for 15 minutes.
The counter resets on a successful sign-in.

**No account enumeration** - an unknown email and a wrong password return the
identical 401 message, so the endpoint cannot be used to discover valid addresses.

**Refresh tokens are stored** - each is a row in `refresh_tokens`, so logout and
password changes can revoke sessions server-side. A stateless JWT alone cannot be
revoked.

**Token type is checked** - `decode_token` verifies the `type` claim, so an access
token cannot be replayed at `/auth/refresh`.

**Self-protection rules** - a user cannot change their own role or deactivate
their own account, which prevents an admin from locking everyone out by mistake.

**Password policy** - minimum 8 characters with upper, lower and a digit, capped
at 72 bytes because bcrypt silently truncates beyond that.

## Tests

```powershell
pytest -v
```

28 tests run against in-memory SQLite, so they need no database:

- 13 authentication tests - login, lockout, refresh rotation, logout revocation,
  password change, registration
- 15 RBAC tests - permission boundaries per role, role hierarchy, system-role
  protection, self-modification guards, pagination metadata

## Next step

Step 3 - Employee, Department and Designation modules: full CRUD, org hierarchy,
manager assignment, employee history tracking and the row-level access rules
(`can_access_employee`) that scope managers to their own reportees.

---

# Step 3: Employee, Department & Designation

## Endpoints

| Method | Path | Guard |
|---|---|---|
| GET | `/employees` | `employee:read` (row-scoped) |
| GET | `/employees/me` | authenticated |
| GET | `/employees/org-chart` | `employee:read` |
| GET | `/employees/{id}` | `employee:read` + row check |
| GET | `/employees/{id}/team` | `employee:read` + row check |
| GET | `/employees/{id}/history` | `employee:read` + row check |
| POST | `/employees` | `employee:create` |
| PATCH | `/employees/{id}` | `employee:update` |
| POST | `/employees/{id}/exit` | `employee:update` |
| DELETE | `/employees/{id}` | `employee:delete` |
| POST | `/employees/import` | `employee:create` |
| GET | `/departments` | `department:read` |
| GET | `/departments/tree` | `department:read` |
| GET | `/departments/{id}` | `department:read` |
| POST/PATCH/DELETE | `/departments` | `department:manage` |
| GET | `/designations` | `department:read` |
| POST/PATCH/DELETE | `/designations` | `department:manage` |

## Two layers of access control

Permission guards decide **whether the endpoint can be called**. Row-level
scoping decides **which records come back**. Both are needed -- a manager holds
`employee:read`, but must not read an unrelated employee's record.

| Role | Rows visible |
|---|---|
| admin, hr | every employee |
| manager | self + direct reportees |
| employee | self only |

`scope_query()` applies this to list endpoints; `assert_can_access()` applies it
to single-record endpoints. The `employee` role deliberately does **not** hold
`employee:read` -- self-service runs through `/employees/me`.

## Automatic history

Changing department, designation, manager, salary, employment type or status
writes an `employee_history` row with the old and new values. A write only
happens when the value actually changes, so a no-op PATCH leaves no trace.

Salary changes additionally compute `last_hike_percent` and stamp
`last_hike_date`.

This is what makes point-in-time reporting possible later: `employees` holds
current state, `employee_history` holds how it got there.

## Cycle prevention

Both hierarchies walk their parent chain before accepting a change:

- `manager_id` -- rejects self-management and any chain that loops back
- `department.parent_id` -- same check for nested departments

Without this, `org-chart` and `departments/tree` would recurse forever.

## Bulk import

`POST /employees/import` takes a CSV with:

```
first_name,last_name,work_email,phone,date_of_joining,
department_code,designation_code,manager_code,employment_type,
work_mode,current_salary
```

Each row commits independently, so one malformed row does not abort the batch.
The response reports created, skipped (duplicate email) and failed counts with a
row number and reason for each failure.

## Tests

71 passing:

- 14 authentication
- 14 RBAC
- 12 department / designation
- 31 employee -- creation, scoping per role, history writing, cycle rejection,
  exit rules, CSV import

Run with `pytest -v`.

---

# Step 4: Attendance, Shift & Leave

## Endpoints

| Method | Path | Guard |
|---|---|---|
| POST | `/attendance/check-in` | linked employee |
| POST | `/attendance/check-out` | linked employee |
| GET | `/attendance/me` | linked employee |
| GET | `/attendance` | `attendance:read_team` or `read_all` |
| GET | `/attendance/summary/{id}` | `attendance:read` + row check |
| POST | `/attendance/regularize` | linked employee |
| GET | `/attendance/regularizations/pending` | `attendance:manage` |
| POST | `/attendance/{id}/regularization` | `attendance:manage` |
| POST | `/attendance/manual` | `attendance:manage` |
| POST | `/attendance/run-daily-marking` | `attendance:manage` |
| GET/POST | `/attendance/holidays` | `attendance:read` / `manage` |
| GET | `/shifts`, `/shifts/{id}` | `attendance:read` |
| GET | `/shifts/roster` | `attendance:read_all` |
| POST/PATCH/DELETE | `/shifts` | `shift:manage` |
| POST | `/shifts/{id}/assign` | `shift:manage` |
| GET/POST/PATCH | `/leaves/types` | `leave:read` / `leave:manage` |
| GET | `/leaves/balance` | linked employee |
| GET | `/leaves/balance/{id}` | `leave:read_team` or `read_all` |
| POST | `/leaves/balance/allocate` | `leave:manage` |
| POST | `/leaves` | linked employee |
| GET | `/leaves/me` | linked employee |
| GET | `/leaves`, `/leaves/pending` | `leave:read_*` / `leave:approve` |
| POST | `/leaves/{id}/approve` `/reject` | `leave:approve` |
| POST | `/leaves/{id}/cancel` | own request |
| POST | `/leaves/carry-forward` | `leave:manage` |

## Night shifts

A shift whose end time is at or before its start time rolls past midnight.
`working_hours` and `is_night_shift` are derived from the times, never supplied.

The harder question is which date the record belongs to. A shift running
22:00 Monday to 06:00 Tuesday is **one Monday record**, not two. So a check-in
at 00:30 is filed against the previous day when the employee is on a night
shift -- `attendance_date_for()` handles this, and it is why the unique
constraint on `(employee_id, attendance_date)` holds.

## Derived, never supplied

`worked_hours`, `overtime_hours`, `late_minutes` and `early_exit_minutes` are
all computed from the timestamps and the assigned shift. A client cannot post
its own hours.

Late is measured against the shift's `grace_period_minutes`, so arriving at
09:10 on a 09:00 shift with 15 minutes grace is on time; 09:45 is 45 minutes
late.

## Forgotten check-outs

`close_forgotten_checkouts()` credits hours up to the shift end rather than
zero -- the person did work -- and stamps the record so HR can see it was
auto-closed. This runs *before* the daily marking pass, otherwise an open
record would be counted as absent.

## Leave balance ledger

Four columns, not one:

```
available = (allocated + carried_forward) - (used + pending)
```

Applying moves days into `pending`. Approval moves them `pending -> used`.
Rejection or cancellation releases them.

Tracking `pending` separately is what stops two simultaneous requests from both
fitting inside the same balance -- the days are reserved the moment the first
request is filed, not when it is approved.

## Chargeable days

Weekends and public holidays inside a range are not charged. Friday to Monday
is two days, not four. A range containing no working days at all is rejected
rather than silently costing nothing.

Half-day leave charges 0.5 and must start and end on the same date.

## Policy enforcement at apply time

- `min_notice_days` -- rejects short-notice requests
- `requires_document` -- rejects sick leave with no attachment
- `max_consecutive_days` -- caps a single run
- overlap detection against existing pending or approved requests
- balance check, skipped for unpaid types

## Carry forward

`POST /leaves/carry-forward?from_year=2025` rolls unused balance into the next
year, capped at `max_carry_forward`. Only types flagged `is_carry_forward`
participate; everything else lapses.

## Tests

120 passing (49 new in this step):

- 26 attendance -- night shift boundaries, grace period, half day, overtime,
  auto-close, daily marking, working-day counting, regularisation
- 23 leave -- ledger transitions, overlap blocking, notice and document rules,
  manager-scoped approval queue, carry-forward cap

---

# Step 5: Payroll

## Endpoints

| Method | Path | Guard |
|---|---|---|
| GET | `/payroll/structures/{employee_id}` | `payroll:manage` |
| POST | `/payroll/structures` | `payroll:manage` |
| GET | `/payroll/runs` | `payroll:read_all` |
| POST | `/payroll/runs` | `payroll:process` |
| GET | `/payroll/runs/{id}` | `payroll:read_all` |
| GET | `/payroll/runs/{id}/summary` | `payroll:read_all` |
| POST | `/payroll/runs/{id}/process` | `payroll:process` |
| POST | `/payroll/runs/{id}/approve` | `payroll:process` |
| POST | `/payroll/runs/{id}/mark-paid` | `payroll:process` |
| GET | `/payroll/runs/{id}/payslips` | `payroll:read_all` |
| GET | `/payroll/payslips/me` | linked employee |
| GET | `/payroll/payslips/{id}` | own, or HR/admin |
| GET | `/payroll/payslips/{id}/pdf` | own, or HR/admin |
| POST | `/payroll/payslips/{id}/adjustments` | `payroll:process` |

## Decimal, not float

Every monetary value is a `Decimal`, quantised to two places with
`ROUND_HALF_UP` at each step. `0.1 + 0.2` is not `0.3` in binary floating
point, and across thousands of payslips that error accumulates. A payslip a
paisa out is a payslip that fails bank reconciliation.

`money()` is the single coercion point; nothing else touches raw arithmetic.

## Loss of pay

Charged at `gross / working_days_in_period`, not a notional thirty. February
has fewer working days than March, so a day off in February costs more -- which
is correct: the salary buys that month's working days.

LOP days = absent days + approved **unpaid** leave + the unworked half of any
half day. Paid leave costs nothing, which is what makes it paid.

## Overtime

Paid at 1.5x the basic hourly rate, derived as
`basic / working_days / 8 hours`. Only hours already recorded on attendance
count -- the payroll module never invents them.

## Effective-dated structures

Creating a new structure closes the previous one the day before the new
effective date. Nothing is overwritten, so a payslip generated last March can
still be explained with the figures that applied then. `active_structure()`
resolves the right one for any date.

A structure effective *earlier* than the current one is rejected -- backdating
would silently change history.

## Immutability

```
draft -> processing -> processed -> approved -> paid
```

Reprocessing a **draft** discards and regenerates its payslips, which is safe.
Once a run is **approved or paid**, both reprocessing and adjustments are
refused.

A correction discovered after payment becomes an arrears line on the *next*
run, via `POST /payslips/{id}/adjustments`. This keeps every payslip matching
what actually left the bank -- mutating a paid payslip would break
reconciliation and destroy the audit trail.

## Skipped employees are reported

An employee with no salary structure in force is skipped, and the reason is
returned in the response rather than being silently omitted. Silent omission
is how someone doesn't get paid.

## PDF payslips

`GET /payroll/payslips/{id}/pdf` renders with reportlab: employee and period
details, earnings and deductions side by side, net pay banded at the bottom.
Amounts use Indian digit grouping (`12,34,567.50`).

## Tests

149 passing (29 new):

- rounding behaviour and `Decimal` arithmetic
- LOP per working day, half days, the cap at gross
- overtime at 1.5x
- effective-dated resolution and backdating rejection
- the full draft -> paid workflow and every state guard
- adjustment allowed on draft, refused on paid
- access control: own payslip only, unless HR
- PDF generation returns a real `%PDF` document

---

# Phase 2, Step 6: Dataset Management & Attrition Prediction

## Endpoints

| Method | Path | Guard |
|---|---|---|
| POST | `/datasets/upload` | `dataset:manage` |
| GET | `/datasets` | `dataset:manage` |
| GET | `/datasets/{id}` | `dataset:manage` |
| GET | `/datasets/{id}/preview` | `dataset:manage` |
| PUT | `/datasets/{id}/target` | `dataset:manage` |
| POST | `/datasets/{id}/validate` | `dataset:manage` |
| DELETE | `/datasets/{id}` | `dataset:manage` |
| POST | `/predictions/train` | `model:train` |
| GET | `/predictions/models` | `prediction:read` |
| GET | `/predictions/models/active` | `prediction:read` |
| GET | `/predictions/models/{id}` | `prediction:read` |
| POST | `/predictions/models/{id}/deploy` | `model:deploy` |
| POST | `/predictions/employee/{id}` | `prediction:run` + row check |
| POST | `/predictions/batch` | `prediction:run` |
| GET | `/predictions` | `prediction:read` (scoped) |
| GET | `/predictions/{id}` | `prediction:read` + row check |
| GET | `/predictions/batches/history` | `prediction:read` |

## What "attrition" means here

A **voluntary** exit within a horizon, 180 days by default. Both are
configurable per training run.

Terminations and retirements are excluded from the positive class by default:
they are the company's decision, not the employee's, so predicting them is a
different problem. Mixing them in teaches the model to predict management
behaviour and calls it attrition risk.

## Target leakage

Columns recorded at or after the exit decision are blocked outright:
`date_of_exit`, `exit_reason`, `status`. They predict the label perfectly and
are unavailable at prediction time -- the classic way an ML project reports 98%
accuracy and fails in production.

A test proves this: it trains on a dataset where `date_of_exit` *is* the answer
and asserts PR-AUC stays near the base rate, confirming the column was removed
rather than used.

Identifier columns, and any column unique per row, are dropped for the same
reason -- they let the model memorise individuals instead of learning patterns.

## Protected attributes

Gender, marital status and date of birth are excluded by default. If HR acts on
a prediction materially driven by marital status, that is a discrimination
exposure. They can be enabled explicitly (`include_protected_attributes: true`)
and the model records which set was used.

Dropping the column does not remove the signal entirely -- proxies remain, and
that limitation belongs in the report rather than being hidden.

## Why accuracy is not the headline metric

With roughly 16% attrition, a model predicting "nobody leaves" scores **84%
accuracy** and is worthless. Every training response therefore reports:

- **precision** -- of those flagged, how many actually left
- **recall** -- of those who left, how many were flagged
- **PR-AUC** -- the honest summary under class imbalance
- **accuracy** *alongside* **baseline_accuracy**, the majority-class rate

Accuracy frequently lands *below* the baseline, because the threshold is tuned
for recall. That is the correct trade, and the response says so in its notes.

## Threshold tuning

0.5 is an arbitrary default. For retention, a false negative (someone leaves
unflagged) costs far more than a false positive (an unnecessary retention
conversation), so the threshold maximises F1 by default, or can be set to reach
a requested recall with `target_recall`.

Class imbalance is handled with `class_weight="balanced"` rather than
resampling, which would distort the calibrated probabilities that the risk
bands depend on.

## Per-employee explanations

Impurity-based importance is a *global* statistic. It says which features
mattered across the training set, not why this person is at risk.

`explainer.explain_row()` re-scores the individual with one feature at a time
reset to the workforce median and measures how far the probability moves. That
difference is the feature's contribution *for that person*. A test confirms two
employees get different top drivers from the same model.

Each prediction also carries a plain-English narrative ending with the caveat
that these are statistical associations, not a statement about intentions.

## Model versioning

Exactly one version is deployed at a time; deploying archives the previous one.
Every prediction records `model_version_id`, so a score from March can be
explained in September with the artifact that actually produced it.

The preprocessing pipeline is fitted *inside* the model pipeline and persisted
with it. Storing an encoder separately from the model is how train/serve skew
creeps in.

`actual_outcome` on each prediction is filled in when someone actually leaves,
which is what makes drift measurable later.

## CLI

```powershell
python -m scripts.train_model --source dataset --dataset-id 1 --deploy
```

Prints the full metrics table, confusion matrix and feature importance bars.

## Tests

185 passing (36 new):

- 14 dataset -- profiling, type detection, target guessing, yes/no label
  normalisation, leakage and protected-attribute reporting, validation failures
- 22 prediction -- metric honesty, threshold tuning, deployment exclusivity,
  scoped listing, risk bands, leakage removal proven by PR-AUC, local
  explanations differing per employee

## Known limitations

**Trained on a snapshot, not point-in-time.** Features are assembled as of
today rather than reconstructed as of each historical prediction date.
`employee_history` holds the data needed to do this properly; it is the first
thing to fix for production use.

**No fairness audit built in.** Protected attributes are excluded, but proxy
correlation is not measured. Group-wise prediction rates would be cheap to add
and belong in the report.

**Intervention effect is correlational.** `risk_score_before` and
`risk_score_after` are recorded, but without a control group there is no way to
separate an intervention working from regression to the mean.

---

# Phase 2 (part 1): Datasets & the Attrition Engine

## Endpoints

| Method | Path | Guard |
|---|---|---|
| POST | `/datasets/upload` | `dataset:manage` |
| GET | `/datasets`, `/datasets/{id}` | `dataset:manage` |
| GET | `/datasets/{id}/preview` | `dataset:manage` |
| POST | `/datasets/{id}/validate` | `dataset:manage` |
| DELETE | `/datasets/{id}` | `dataset:manage` |
| POST | `/predictions/train` | `model:train` |
| GET | `/predictions/models` | `prediction:read` |
| GET | `/predictions/models/active` | `prediction:read` |
| GET | `/predictions/models/{id}` | `prediction:read` |
| POST | `/predictions/models/{id}/deploy` | `model:deploy` |
| POST | `/predictions/employee/{id}` | `prediction:run` + row check |
| POST | `/predictions/batch` | `prediction:run` |
| GET | `/predictions`, `/predictions/batches` | `prediction:read` |
| GET | `/predictions/employee/{id}/history` | `prediction:read` |
| POST | `/predictions/outcomes` | `prediction:run` |

## Getting a working model

```powershell
python -m scripts.generate_demo_data --count 250
```

Then in Swagger: train, deploy, batch.

## Leakage control

A feature is only usable if its value would have been known at the moment of
prediction. These are excluded by name:

```
date_of_exit, exit_reason, status,
current_risk_score, current_risk_level, last_risk_evaluated_at
```

They are recorded *because* someone left. Including them produces a model that
scores near-perfect in testing and is useless in production.

**Two leaks were found and fixed during development**, both worth knowing about:

1. The demo generator originally created attendance only for current staff.
   Leavers had no rows, so `absence_rate` was 0 for every leaver and the model
   learned "no attendance data = left". Fixed by generating attendance for
   leavers up to their exit date, and by returning `None` rather than `0.0`
   when a window is empty, so it is imputed instead of read as perfect
   attendance.

2. A `attendance_days_observed` count was briefly added as a feature. Leavers
   naturally have fewer observed days, so the count encoded the label directly
   and PR-AUC went to 1.0. Removed.

The lesson in both cases is the same: **a perfect score is a bug report.**
`test_perfect_scores_would_signal_leakage` asserts PR-AUC stays below 0.999 as
a standing canary.

## Point-in-time correctness

The behaviour window (absence rate, late rate, overtime ratio, leave taken) is
anchored **per employee**: it ends today for current staff and on the exit date
for leavers. Anchoring everyone at today would leave recent leavers with an
empty window, which is the same leak in a different shape.

## Fairness

Gender, marital status and date of birth are excluded by default. They appear
in standard HR datasets and are often predictive, but acting on a prediction
materially driven by marital status is a discrimination exposure.

`include_protected_attributes: true` turns them on, so the decision is explicit
and appears in the model's stored config where a reviewer can see it.

## Metrics that mean something

With attrition at 15-25%, a model predicting "nobody leaves" scores 75-85%
accuracy. So the evaluation reports:

- **precision, recall, F1** at the chosen threshold
- **PR-AUC** -- the right summary for an imbalanced positive class
- **accuracy alongside `majority_class_baseline_accuracy`**, so accuracy can
  never be quoted in isolation
- **a threshold sweep** at 0.2 to 0.7 with precision, recall and the number
  flagged at each

A representative run on 300 generated employees (26% attrition):

```
precision 0.74   recall 0.74   F1 0.74
PR-AUC 0.841     ROC-AUC 0.868
accuracy 0.867   majority baseline 0.747
```

0.5 is not the right operating point for retention. A false positive costs one
awkward conversation; a false negative costs an employee. The sweep exists so
that trade can be made deliberately.

## Explanations

Global feature importance describes the model; it cannot say why *this* person
scored 0.82. The explainer uses **occlusion**: each feature is replaced with
the population's typical value and the model re-scored, so the contribution is
measured from the model rather than inferred on its behalf. One prediction per
feature, ~25 features, fast enough to run inline.

SHAP would be the production choice; this is the same idea without the
dependency.

## Model versioning

Exactly one version is active at a time. Deploying archives the previous one.
Every artifact stores its own feature list, threshold and training config, so a
prediction made in March can still be explained in September.

`POST /predictions/outcomes` stamps the real outcome onto past predictions,
which is the only way to measure the model against reality rather than against
the test split it was born with.

## Tests

184 passing (35 new):

- 13 dataset -- profiling, type inference, binary target coercion, validation
  errors and warnings
- 22 prediction -- leakage exclusions, protected-attribute defaults, per-employee
  window anchoring, honest metrics, the perfect-score canary, deployment
  exclusivity, batch scoring, explanations, outcome recording

---

# Phase 2 (part 2): Risk, Alerts, Forecasting & Interventions

## Endpoints

| Method | Path | Guard |
|---|---|---|
| GET | `/risk/scores` | `risk:read_team` or `read_all` |
| GET | `/risk/employee/{id}` | scoped |
| GET | `/risk/employee/{id}/history` | scoped |
| POST | `/risk/evaluate` | `risk:manage` |
| GET | `/risk/heatmap` | `risk:read_all` |
| GET | `/risk/alerts` | scoped |
| POST | `/risk/alerts/{id}/acknowledge` `/resolve` | `risk:manage` |
| GET/POST/PATCH/DELETE | `/alert-rules` | `alert_rule:manage` |
| POST | `/alert-rules/evaluate` | `alert_rule:manage` |
| GET | `/alert-rules/{id}/triggers` | `alert_rule:manage` |
| GET/POST | `/forecasting` | `forecast:manage` |
| POST/GET | `/forecasting/{id}/scenarios` | `forecast:manage` |
| GET/POST/PATCH | `/interventions` | `intervention:manage` |
| POST | `/interventions/{id}/actions` | `intervention:manage` |
| GET | `/interventions/effectiveness` | `intervention:manage` |
| GET | `/analytics/attrition/*` | `analytics:read_all` |

## Composite risk score

The model probability answers "will this person leave". It does not answer
"why, and what could be done". So the composite blends the model output with
sub-scores that map to actions someone can actually take:

| Component | Weight |
|---|---|
| ML probability | 0.35 |
| Compensation | 0.15 |
| Engagement | 0.15 |
| Workload | 0.10 |
| Attendance | 0.10 |
| Performance | 0.05 |
| Tenure | 0.05 |
| Leave pattern | 0.05 |

Every sub-score is 0-100, and the weights used are stored on each score row, so
a dashboard number can always be taken apart.

**When no model is deployed, the ML weight is redistributed** across the
remaining components rather than scored as zero. Scoring zero would quietly
halve everyone's risk and make the whole board look green.

## Alert engine

Two mechanisms keep this from becoming a notification firehose:

- **Cooldown** -- the same rule cannot re-fire for the same employee within
  `cooldown_hours`
- **Open-alert de-duplication** -- a rule is skipped for anyone who already has
  an unresolved alert from it

The evaluation response returns a `suppressed` count so you can see how many
matches were withheld. HR that receives 200 emails from one scoring run stops
reading them.

## Forecasting

Ordinary least squares over the monthly history. Prediction intervals come from
the residual standard error and widen with distance from the fitted data --
a projection six months out genuinely is less certain than one month out.

With fewer than four historical periods it falls back to the mean and says so
in the response, rather than fitting a trend line through three points.

Every forecast carries an `assumptions.caveat`: linear extrapolation cannot
anticipate a reorganisation, a market shift or a policy change.

## Scenarios are assumptions, not findings

"What if we raise salaries 8%" applies an assumed elasticity -- 1% of salary
maps to 0.4 percentage points of attrition -- arithmetically to the projection.
The model is not re-fitted. That assumption is returned in `results.assumption`
so nobody mistakes it for a measured effect.

## Interventions and the causation problem

Plans capture `risk_score_before` at creation and `risk_score_after` at
completion. The effectiveness endpoint reports the observed change **and a
caveat in the response body**:

> High scores drift toward the mean without any intervention, and there is no
> control group here, so this shows correlation only.

This is the honest answer to "how do you know the intervention worked". Proving
it would need a randomised holdout, which is a policy decision rather than an
engineering one.

Completing a plan requires every action to be closed first, so a plan cannot be
marked done with outstanding work on it.

## Attrition analytics

`by-tenure` is the most useful of these. The first year almost always dominates,
and split that way "we have an attrition problem" often turns out to be "we
have an onboarding problem".

`overview` separates voluntary from involuntary exits. A termination is the
company's decision; lumping the two together hides the number the business can
actually influence.

## Two bugs found by the tests

1. **Same-day risk evaluations ordered non-deterministically.** The history
   query sorted by `evaluation_date` alone, so two scores on the same date came
   back in arbitrary order and `previous_score` could read as null. Fixed with
   an `id` tie-break.

2. **The effectiveness caveat vanished when there were no completed plans.**
   The empty-state message replaced it entirely. The causal warning now appears
   in both branches.

---

# Phase 1 completion & Phase 3: the backend is complete

**181 HTTP routes, 2 WebSocket routes, 315 tests passing.**

## What was added

**Phase 1 completion** — Notifications (preferences per category and channel),
Chat (one-to-one, REST and WebSocket), Documents (validated vault with a
verification workflow), Dashboard (role-scoped), Monitoring (polling snapshot
plus presence).

**Phase 3** — Reports (CSV/Excel/PDF/JSON), Audit (append-only with redaction),
Workflow & Tasks, Performance Reviews (staged), AI Recommendations (rule-based),
Advanced Search, Workforce Stability Engine.

## Decisions worth defending

**Uploads are validated by content, not extension.** `file_handler` checks size,
a blocked-extension list, double extensions like `report.pdf.exe`, and magic
bytes. Renaming a shell script to `.pdf` is rejected because the first bytes
are not `%PDF`. There is a test for exactly that.

**Documents are served through the API, not the static mount.** A file under
`/uploads` would be readable by anyone who guessed the path. The download route
enforces the visibility rules, so a payslip marked private is not readable by
the line manager.

**Chat conversations are normalised pairs.** The smaller user id is always
`user_one_id`, which is what makes the unique constraint work — without it,
A-to-B and B-to-A would create two separate threads.

**One dashboard endpoint, not four.** The tiles overlap heavily; what changes
is the scope of the data and which sections appear. An employee gets their own
section, a manager gets a team block scoped to reportees, HR gets the
organisation plus the risk distribution.

**Audit logs redact before writing.** Passwords, tokens, bank account numbers
and PAN never enter the trail, even in the `old_values`/`new_values` diff.
There is no update or delete route in the audit module, and none should be
added.

**Performance reviews check the actor at each transition.** A manager cannot
skip the self-review; an employee cannot sign off their own final rating. The
final rating writes back to `employees.last_performance_rating`, which then
feeds the risk model.

**Recommendations are rule-based on purpose.** A recommendation must be
explainable to the manager acting on it. "Bottom quartile of the band, no
revision in 26 months" is actionable; "the model said 0.82" is not. Each rule
returns its own evidence in `supporting_data`, and anything already open for
the same reason is suppressed rather than repeated.

**The stability index can be taken apart.** Every metric is stored with its raw
value, normalised score, weight and benchmark. The weights are a stated
judgement, not a discovered truth, and they are returned with every snapshot.

**Report generation is capped at 20,000 rows.** Above that it refuses with a
message asking you to narrow the filter, rather than quietly timing out. A
background worker would be the production answer; this project does not run a
queue, so the cap is the honest mitigation.

## Known limitations, stated plainly

**WebSocket state is in-process.** `uvicorn --workers 4` breaks it: a socket
held by worker 2 is unreachable from worker 3, and the message is silently
lost. Horizontal scaling needs Redis pub/sub. The app is designed to run
single-worker.

**APScheduler runs per instance.** Two application instances means every
nightly job fires twice. Production needs a dedicated scheduler process or a
distributed lock.

**WebSocket tokens travel in the query string.** Browsers cannot set headers on
a WebSocket handshake. That puts the token where it may reach server logs; the
mitigations are short token lifetimes and not logging query strings.

**Search uses `ILIKE '%term%'`.** This cannot use a B-tree index and degrades
linearly with table size. Fine at a few thousand employees; at a few hundred
thousand the answer is a PostgreSQL `tsvector` column with a GIN index.

**Tests run on SQLite.** Fast and dependency-free, but blind to PostgreSQL
specifics: JSONB operators, `ILIKE` collation behaviour, transactional DDL.
A separate CI run against PostgreSQL would close that gap.

## Test coverage

| Suite | Tests |
|---|---|
| Auth | 14 |
| RBAC | 14 |
| Departments | 12 |
| Employees | 31 |
| Attendance | 26 |
| Leave | 23 |
| Payroll | 29 |
| Datasets | 13 |
| Predictions | 22 |
| Risk & forecasting | 38 |
| Notifications, chat, documents, dashboard | 41 |
| Phase 3 | 52 |
| **Total** | **315** |

## Scheduled jobs

Registered in `app/tasks/scheduler.py`, started only when `APP_ENV=production`:

| Job | Schedule |
|---|---|
| Daily attendance marking | 01:00 |
| Risk scoring + alert rules | 02:00 |
| Document expiry | 03:00 |
| Stability snapshot | Mondays 04:00 |
| Housekeeping (purge expired) | 05:00 |


# WorkForce AI Pro — Frontend

React 18 + Vite + Tailwind CSS, talking to the FastAPI backend over Axios, with
Recharts for the dashboards.

## Running it

The backend must be up first:

```powershell
cd ..\backend
uvicorn app.main:app --reload
```

Then, in a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 and sign in with the account the seed script
created.

No `.env` is needed for local development. Vite proxies `/api` to
`http://127.0.0.1:8000`, so the browser stays on a single origin and CORS never
comes into it. Set `VITE_API_BASE_URL` only when the frontend is served
separately from the API.

## Structure

```
src/
├── api/
│   ├── client.js        axios instance, auth header, refresh queue
│   └── endpoints.js     every call, grouped by module
├── context/
│   └── AuthContext.jsx  session, permissions, sign in/out
├── components/
│   ├── Layout.jsx  Sidebar.jsx  Topbar.jsx  ProtectedRoute.jsx
│   └── ui/          Card, Badge, Table, States
├── pages/
│   ├── Login.jsx  Dashboard.jsx
│   ├── Employees.jsx  EmployeeDetail.jsx
│   ├── Attendance.jsx  Leave.jsx  Payroll.jsx
│   ├── Attrition.jsx  RiskMonitor.jsx  Models.jsx
│   └── Notifications.jsx  Errors.jsx
├── hooks/useApi.js      loading/error/data, plus polling
├── utils/format.js      currency, dates, risk colours
└── config/nav.js        navigation, filtered by permission
```

## The refresh interceptor

The dashboard fires several requests at once. When the access token expires,
all of them come back 401 together.

Refreshing once per failed request would fire several refresh calls in
parallel. Since the backend revokes refresh tokens on logout and password
change, concurrent rotation is exactly the pattern that produces intermittent
"why was I logged out" reports.

So the first 401 starts a single refresh. Every other request that fails while
it is in flight parks itself in a queue and is replayed with the new token once
it lands. If the refresh itself fails, the queue is rejected, tokens are
cleared, and `AuthContext` drops the user back to the login screen rather than
leaving them on a page that will never load.

The `/auth/refresh` and `/auth/login` calls are excluded, so a failed login
cannot trigger a refresh loop.

## Permission-driven navigation

`config/nav.js` keys off permission codes, not role names:

```js
{ to: "/attrition", label: "Attrition Analytics", permission: "analytics:read_all" }
```

Keying off roles would mean editing this file every time a permission moved.
Keying off the code means the navigation follows whatever the backend actually
grants.

**Hiding a button is not a security control.** Every one of these permissions is
enforced server-side on the route itself. The UI check exists so people are not
shown things they cannot use; anyone can still call the API directly, and the
API is where the decision is made. `ProtectedRoute` redirects to `/forbidden`
rather than pretending the page does not exist.

## Token storage

Tokens live in `localStorage`. That is readable by any script on the page, so
it trades XSS resistance for simplicity and survives a refresh.

The alternative is an httpOnly cookie, which XSS cannot read — but that needs
the backend to set and clear cookies, plus CSRF protection, since cookies are
sent automatically. Given a 60-minute access token and a same-origin dev proxy,
`localStorage` is the reasonable choice here, and it is a deliberate one rather
than a default.

## Polling, not sockets, for the dashboard

`usePolling` refreshes the live snapshot every 30 seconds and pauses while the
tab is hidden, so a backgrounded dashboard stops making requests.

Headcount does not change second to second, so polling is the right tool. The
backend's WebSocket channel is there for events that genuinely need to arrive
immediately — chat messages and critical risk alerts.

## The page worth demonstrating

`/employees/:id` → **Score attrition risk**.

It returns the probability, the risk band, and the named factors behind it —
each with this person's value against the population typical, and a bar showing
which way it pushes. That comes from the backend's occlusion explainer: every
feature is replaced with the population's typical value and the model
re-scored, so the contribution is measured rather than inferred.

The composite risk panel below it breaks the 0–100 score into its eight
weighted components. When no model is deployed it says so, and explains that
the ML weight has been redistributed rather than scored as zero.

## Bundle

```
index    64 kB   application code
vendor   65 kB   axios, icons, dates
react   165 kB   react, react-dom, router
charts  433 kB   recharts and its d3 dependencies
```

Recharts is most of the weight and only three pages use it, so it is split into
its own chunk. The login screen and employee list no longer download charting
code they never render, and the vendor chunks stay cached across deploys.

## Known gaps

- **No test suite.** The backend has 324 tests; this has none. Vitest plus
  React Testing Library would be the next step, starting with the refresh
  interceptor, since that is the piece with real logic in it.
- **No WebSocket client yet.** The backend exposes `/ws/chat` and
  `/ws/monitoring`; the UI currently polls instead.
- **Chat and Documents have no screens.** The API supports both.
- **Employee create and edit are read-only in the UI.** The endpoints exist.
