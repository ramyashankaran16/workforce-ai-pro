# WorkForce AI Pro - Database Schema

Total tables: **59**

Generated from the SQLAlchemy metadata in `app/models/`.

## Authentication & RBAC

### `users`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| email | VARCHAR(255) | N | IDX | unique |
| username | VARCHAR(80) | Y |  | unique |
| hashed_password | VARCHAR(255) | N |  |  |
| full_name | VARCHAR(150) | N |  |  |
| phone | VARCHAR(20) | Y |  |  |
| avatar_url | VARCHAR(500) | Y |  |  |
| role_id | INTEGER | N | FK | -> roles.id |
| status | VARCHAR(40) | N | IDX |  |
| is_email_verified | BOOLEAN | N |  |  |
| must_change_password | BOOLEAN | N |  |  |
| failed_login_attempts | INTEGER | N |  |  |
| locked_until | DATETIME | Y |  |  |
| last_login_at | DATETIME | Y |  |  |
| last_login_ip | VARCHAR(64) | Y |  |  |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |
| is_deleted | BOOLEAN | N | IDX |  |
| deleted_at | DATETIME | Y |  |  |

### `refresh_tokens`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| user_id | INTEGER | N | FK | -> users.id |
| token | VARCHAR(512) | N | IDX |  |
| expires_at | DATETIME | N |  |  |
| is_revoked | BOOLEAN | N |  |  |
| revoked_at | DATETIME | Y |  |  |
| user_agent | VARCHAR(300) | Y |  |  |
| ip_address | VARCHAR(64) | Y |  |  |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |

### `roles`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| name | VARCHAR(50) | N | IDX | unique |
| display_name | VARCHAR(100) | N |  |  |
| description | TEXT | Y |  |  |
| hierarchy_level | INTEGER | N |  |  |
| is_system_role | BOOLEAN | N |  |  |
| is_active | BOOLEAN | N |  |  |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |

### `permissions`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| code | VARCHAR(100) | N | IDX | unique |
| name | VARCHAR(150) | N |  |  |
| module | VARCHAR(60) | N | IDX |  |
| description | TEXT | Y |  |  |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |

### `role_permissions`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| role_id | INTEGER | N | PK | -> roles.id |
| permission_id | INTEGER | N | PK | -> permissions.id |


## Organisation Structure

### `departments`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| code | VARCHAR(30) | N | IDX | unique |
| name | VARCHAR(120) | N | IDX |  |
| description | TEXT | Y |  |  |
| parent_id | INTEGER | Y | FK | -> departments.id |
| head_employee_id | INTEGER | Y | FK | -> employees.id |
| location | VARCHAR(150) | Y |  |  |
| budget | NUMERIC(14, 2) | Y |  |  |
| headcount_limit | INTEGER | Y |  |  |
| is_active | BOOLEAN | N |  |  |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |
| is_deleted | BOOLEAN | N | IDX |  |
| deleted_at | DATETIME | Y |  |  |

### `designations`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| title | VARCHAR(120) | N | IDX |  |
| code | VARCHAR(30) | Y |  | unique |
| description | TEXT | Y |  |  |
| department_id | INTEGER | Y | FK | -> departments.id |
| level | INTEGER | N |  |  |
| min_salary | NUMERIC(12, 2) | Y |  |  |
| max_salary | NUMERIC(12, 2) | Y |  |  |
| is_active | BOOLEAN | N |  |  |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |
| is_deleted | BOOLEAN | N | IDX |  |
| deleted_at | DATETIME | Y |  |  |

### `employees`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| employee_code | VARCHAR(30) | N | IDX | unique |
| user_id | INTEGER | Y | FK | -> users.id, unique |
| first_name | VARCHAR(80) | N |  |  |
| last_name | VARCHAR(80) | Y |  |  |
| personal_email | VARCHAR(255) | Y |  |  |
| work_email | VARCHAR(255) | N | IDX |  |
| phone | VARCHAR(20) | Y |  |  |
| date_of_birth | DATE | Y |  |  |
| gender | VARCHAR(40) | Y |  |  |
| marital_status | VARCHAR(40) | Y |  |  |
| address | TEXT | Y |  |  |
| city | VARCHAR(80) | Y |  |  |
| state | VARCHAR(80) | Y |  |  |
| country | VARCHAR(80) | Y |  |  |
| postal_code | VARCHAR(20) | Y |  |  |
| emergency_contact_name | VARCHAR(120) | Y |  |  |
| emergency_contact_phone | VARCHAR(20) | Y |  |  |
| department_id | INTEGER | Y | FK | -> departments.id |
| designation_id | INTEGER | Y | FK | -> designations.id |
| manager_id | INTEGER | Y | FK | -> employees.id |
| employment_type | VARCHAR(40) | N |  |  |
| work_mode | VARCHAR(40) | N |  |  |
| status | VARCHAR(40) | N | IDX |  |
| date_of_joining | DATE | N | IDX |  |
| confirmation_date | DATE | Y |  |  |
| date_of_exit | DATE | Y |  |  |
| exit_reason | TEXT | Y |  |  |
| notice_period_days | INTEGER | N |  |  |
| work_location | VARCHAR(150) | Y |  |  |
| current_salary | NUMERIC(12, 2) | Y |  |  |
| last_hike_percent | FLOAT | Y |  |  |
| last_hike_date | DATE | Y |  |  |
| last_promotion_date | DATE | Y |  |  |
| total_experience_years | FLOAT | Y |  |  |
| education_level | VARCHAR(80) | Y |  |  |
| distance_from_home_km | FLOAT | Y |  |  |
| num_companies_worked | INTEGER | Y |  |  |
| training_hours_last_year | FLOAT | Y |  |  |
| business_travel_frequency | VARCHAR(50) | Y |  |  |
| overtime_flag | BOOLEAN | N |  |  |
| job_satisfaction_score | FLOAT | Y |  |  |
| work_life_balance_score | FLOAT | Y |  |  |
| environment_satisfaction_score | FLOAT | Y |  |  |
| last_performance_rating | FLOAT | Y |  |  |
| current_risk_score | FLOAT | Y | IDX |  |
| current_risk_level | VARCHAR(20) | Y | IDX |  |
| last_risk_evaluated_at | DATETIME | Y |  |  |
| profile_image | VARCHAR(500) | Y |  |  |
| bio | TEXT | Y |  |  |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |
| is_deleted | BOOLEAN | N | IDX |  |
| deleted_at | DATETIME | Y |  |  |

### `employee_history`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| employee_id | INTEGER | N | FK | -> employees.id |
| event_type | VARCHAR(40) | N | IDX |  |
| effective_date | DATE | N |  |  |
| field_name | VARCHAR(80) | Y |  |  |
| old_value | VARCHAR(255) | Y |  |  |
| new_value | VARCHAR(255) | Y |  |  |
| remarks | TEXT | Y |  |  |
| changed_by_id | INTEGER | Y | FK | -> users.id |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |


## Attendance & Shifts

### `shifts`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| name | VARCHAR(80) | N |  | unique |
| code | VARCHAR(20) | N |  | unique |
| shift_type | VARCHAR(40) | N |  |  |
| start_time | TIME | N |  |  |
| end_time | TIME | N |  |  |
| break_minutes | INTEGER | N |  |  |
| working_hours | FLOAT | N |  |  |
| grace_period_minutes | INTEGER | N |  |  |
| half_day_threshold_hours | FLOAT | N |  |  |
| is_night_shift | BOOLEAN | N |  |  |
| is_active | BOOLEAN | N |  |  |
| description | TEXT | Y |  |  |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |
| is_deleted | BOOLEAN | N | IDX |  |
| deleted_at | DATETIME | Y |  |  |

### `shift_assignments`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| employee_id | INTEGER | N | FK | -> employees.id |
| shift_id | INTEGER | N | FK | -> shifts.id |
| start_date | DATE | N | IDX |  |
| end_date | DATE | Y |  |  |
| is_active | BOOLEAN | N |  |  |
| assigned_by_id | INTEGER | Y | FK | -> users.id |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |

### `attendances`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| employee_id | INTEGER | N | FK | -> employees.id |
| shift_id | INTEGER | Y | FK | -> shifts.id |
| attendance_date | DATE | N | IDX |  |
| check_in | DATETIME | Y |  |  |
| check_out | DATETIME | Y |  |  |
| check_in_ip | VARCHAR(64) | Y |  |  |
| check_out_ip | VARCHAR(64) | Y |  |  |
| check_in_location | VARCHAR(200) | Y |  |  |
| status | VARCHAR(40) | N | IDX |  |
| worked_hours | FLOAT | N |  |  |
| overtime_hours | FLOAT | N |  |  |
| late_minutes | INTEGER | N |  |  |
| early_exit_minutes | INTEGER | N |  |  |
| is_remote | BOOLEAN | N |  |  |
| regularization_status | VARCHAR(40) | N |  |  |
| regularization_reason | TEXT | Y |  |  |
| approved_by_id | INTEGER | Y | FK | -> users.id |
| remarks | TEXT | Y |  |  |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |

### `holidays`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| name | VARCHAR(120) | N |  |  |
| holiday_date | DATE | N | IDX |  |
| is_optional | BOOLEAN | N |  |  |
| location | VARCHAR(120) | Y |  |  |
| description | TEXT | Y |  |  |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |


## Leave Management

### `leave_types`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| name | VARCHAR(80) | N |  | unique |
| code | VARCHAR(20) | N |  | unique |
| description | TEXT | Y |  |  |
| annual_quota | FLOAT | N |  |  |
| max_consecutive_days | INTEGER | Y |  |  |
| min_notice_days | INTEGER | N |  |  |
| is_paid | BOOLEAN | N |  |  |
| is_carry_forward | BOOLEAN | N |  |  |
| max_carry_forward | FLOAT | N |  |  |
| requires_document | BOOLEAN | N |  |  |
| applicable_gender | VARCHAR(20) | Y |  |  |
| color_code | VARCHAR(10) | Y |  |  |
| is_active | BOOLEAN | N |  |  |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |
| is_deleted | BOOLEAN | N | IDX |  |
| deleted_at | DATETIME | Y |  |  |

### `leave_balances`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| employee_id | INTEGER | N | FK | -> employees.id |
| leave_type_id | INTEGER | N | FK | -> leave_types.id |
| year | INTEGER | N | IDX |  |
| allocated | FLOAT | N |  |  |
| carried_forward | FLOAT | N |  |  |
| used | FLOAT | N |  |  |
| pending | FLOAT | N |  |  |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |

### `leave_requests`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| employee_id | INTEGER | N | FK | -> employees.id |
| leave_type_id | INTEGER | N | FK | -> leave_types.id |
| start_date | DATE | N | IDX |  |
| end_date | DATE | N | IDX |  |
| duration | VARCHAR(40) | N |  |  |
| total_days | FLOAT | N |  |  |
| reason | TEXT | N |  |  |
| contact_during_leave | VARCHAR(50) | Y |  |  |
| attachment_path | VARCHAR(500) | Y |  |  |
| status | VARCHAR(40) | N | IDX |  |
| approver_id | INTEGER | Y | FK | -> employees.id |
| approved_at | DATETIME | Y |  |  |
| approver_remarks | TEXT | Y |  |  |
| cancelled_at | DATETIME | Y |  |  |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |


## Payroll

### `salary_components`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| name | VARCHAR(80) | N |  | unique |
| code | VARCHAR(20) | N |  | unique |
| component_type | VARCHAR(40) | N |  |  |
| is_percentage | BOOLEAN | N |  |  |
| percentage_of | VARCHAR(30) | Y |  |  |
| default_value | NUMERIC(12, 2) | N |  |  |
| is_taxable | BOOLEAN | N |  |  |
| is_active | BOOLEAN | N |  |  |
| display_order | INTEGER | N |  |  |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |

### `salary_structures`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| employee_id | INTEGER | N | FK | -> employees.id |
| ctc | NUMERIC(12, 2) | N |  |  |
| basic_salary | NUMERIC(12, 2) | N |  |  |
| hra | NUMERIC(12, 2) | N |  |  |
| conveyance_allowance | NUMERIC(12, 2) | N |  |  |
| medical_allowance | NUMERIC(12, 2) | N |  |  |
| special_allowance | NUMERIC(12, 2) | N |  |  |
| provident_fund | NUMERIC(12, 2) | N |  |  |
| professional_tax | NUMERIC(12, 2) | N |  |  |
| income_tax | NUMERIC(12, 2) | N |  |  |
| other_deductions | NUMERIC(12, 2) | N |  |  |
| pay_frequency | VARCHAR(40) | N |  |  |
| effective_from | DATE | N | IDX |  |
| effective_to | DATE | Y |  |  |
| is_active | BOOLEAN | N | IDX |  |
| bank_name | VARCHAR(120) | Y |  |  |
| bank_account_number | VARCHAR(40) | Y |  |  |
| ifsc_code | VARCHAR(20) | Y |  |  |
| pan_number | VARCHAR(20) | Y |  |  |
| created_by_id | INTEGER | Y | FK | -> users.id |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |

### `payroll_runs`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| reference | VARCHAR(40) | N | IDX | unique |
| month | INTEGER | N |  |  |
| year | INTEGER | N |  |  |
| period_start | DATE | N |  |  |
| period_end | DATE | N |  |  |
| status | VARCHAR(40) | N | IDX |  |
| total_employees | INTEGER | N |  |  |
| total_gross | NUMERIC(16, 2) | N |  |  |
| total_deductions | NUMERIC(16, 2) | N |  |  |
| total_net | NUMERIC(16, 2) | N |  |  |
| processed_at | DATETIME | Y |  |  |
| paid_at | DATETIME | Y |  |  |
| error_message | TEXT | Y |  |  |
| notes | TEXT | Y |  |  |
| processed_by_id | INTEGER | Y | FK | -> users.id |
| approved_by_id | INTEGER | Y | FK | -> users.id |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |

### `payslips`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| payroll_run_id | INTEGER | N | FK | -> payroll_runs.id |
| employee_id | INTEGER | N | FK | -> employees.id |
| slip_number | VARCHAR(50) | N |  | unique |
| working_days | FLOAT | N |  |  |
| present_days | FLOAT | N |  |  |
| paid_leave_days | FLOAT | N |  |  |
| unpaid_leave_days | FLOAT | N |  |  |
| overtime_hours | FLOAT | N |  |  |
| gross_earnings | NUMERIC(12, 2) | N |  |  |
| total_deductions | NUMERIC(12, 2) | N |  |  |
| net_pay | NUMERIC(12, 2) | N |  |  |
| status | VARCHAR(40) | N |  |  |
| pdf_path | VARCHAR(500) | Y |  |  |
| remarks | TEXT | Y |  |  |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |

### `payslip_items`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| payslip_id | INTEGER | N | FK | -> payslips.id |
| component_name | VARCHAR(80) | N |  |  |
| component_type | VARCHAR(40) | N |  |  |
| amount | NUMERIC(12, 2) | N |  |  |
| display_order | INTEGER | N |  |  |


## Notifications & Chat

### `notifications`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| user_id | INTEGER | N | FK | -> users.id |
| title | VARCHAR(200) | N |  |  |
| message | TEXT | N |  |  |
| notification_type | VARCHAR(40) | N |  |  |
| category | VARCHAR(40) | N | IDX |  |
| priority | VARCHAR(40) | N | IDX |  |
| channel | VARCHAR(40) | N |  |  |
| reference_type | VARCHAR(60) | Y |  |  |
| reference_id | INTEGER | Y |  |  |
| action_url | VARCHAR(500) | Y |  |  |
| is_read | BOOLEAN | N | IDX |  |
| read_at | DATETIME | Y |  |  |
| is_sent | BOOLEAN | N |  |  |
| sent_at | DATETIME | Y |  |  |
| expires_at | DATETIME | Y |  |  |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |

### `notification_preferences`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| user_id | INTEGER | N | FK | -> users.id |
| category | VARCHAR(40) | N |  |  |
| in_app_enabled | BOOLEAN | N |  |  |
| email_enabled | BOOLEAN | N |  |  |
| sms_enabled | BOOLEAN | N |  |  |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |

### `conversations`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| user_one_id | INTEGER | N | FK | -> users.id |
| user_two_id | INTEGER | N | FK | -> users.id |
| last_message_preview | VARCHAR(255) | Y |  |  |
| last_message_at | DATETIME | Y | IDX |  |
| is_archived | BOOLEAN | N |  |  |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |

### `messages`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| conversation_id | INTEGER | N | FK | -> conversations.id |
| sender_id | INTEGER | N | FK | -> users.id |
| content | TEXT | N |  |  |
| message_type | VARCHAR(40) | N |  |  |
| attachment_path | VARCHAR(500) | Y |  |  |
| attachment_name | VARCHAR(255) | Y |  |  |
| attachment_size | INTEGER | Y |  |  |
| is_read | BOOLEAN | N | IDX |  |
| read_at | DATETIME | Y |  |  |
| is_edited | BOOLEAN | N |  |  |
| edited_at | DATETIME | Y |  |  |
| is_deleted | BOOLEAN | N |  |  |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |


## Documents

### `document_categories`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| name | VARCHAR(80) | N |  | unique |
| code | VARCHAR(30) | N |  | unique |
| description | TEXT | Y |  |  |
| is_mandatory | BOOLEAN | N |  |  |
| requires_expiry | BOOLEAN | N |  |  |
| allowed_extensions | VARCHAR(200) | N |  |  |
| max_size_mb | INTEGER | N |  |  |
| is_active | BOOLEAN | N |  |  |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |

### `documents`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| employee_id | INTEGER | N | FK | -> employees.id |
| category_id | INTEGER | Y | FK | -> document_categories.id |
| title | VARCHAR(200) | N |  |  |
| description | TEXT | Y |  |  |
| file_name | VARCHAR(255) | N |  |  |
| file_path | VARCHAR(500) | N |  |  |
| file_type | VARCHAR(30) | Y |  |  |
| file_size | INTEGER | Y |  |  |
| version | INTEGER | N |  |  |
| status | VARCHAR(40) | N | IDX |  |
| visibility | VARCHAR(40) | N |  |  |
| issue_date | DATE | Y |  |  |
| expiry_date | DATE | Y | IDX |  |
| uploaded_by_id | INTEGER | Y | FK | -> users.id |
| verified_by_id | INTEGER | Y | FK | -> users.id |
| verified_at | DATETIME | Y |  |  |
| rejection_reason | TEXT | Y |  |  |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |
| is_deleted | BOOLEAN | N | IDX |  |
| deleted_at | DATETIME | Y |  |  |


## Datasets & Models

### `datasets`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| name | VARCHAR(150) | N | IDX |  |
| description | TEXT | Y |  |  |
| file_name | VARCHAR(255) | N |  |  |
| file_path | VARCHAR(500) | N |  |  |
| file_size | INTEGER | Y |  |  |
| file_format | VARCHAR(20) | N |  |  |
| total_rows | INTEGER | N |  |  |
| total_columns | INTEGER | N |  |  |
| target_column | VARCHAR(100) | Y |  |  |
| positive_class_ratio | FLOAT | Y |  |  |
| missing_value_count | INTEGER | N |  |  |
| duplicate_row_count | INTEGER | N |  |  |
| status | VARCHAR(40) | N | IDX |  |
| validation_errors | JSON | Y |  |  |
| statistics | JSON | Y |  |  |
| is_default | BOOLEAN | N |  |  |
| processed_at | DATETIME | Y |  |  |
| uploaded_by_id | INTEGER | Y | FK | -> users.id |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |
| is_deleted | BOOLEAN | N | IDX |  |
| deleted_at | DATETIME | Y |  |  |

### `dataset_columns`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| dataset_id | INTEGER | N | FK | -> datasets.id |
| name | VARCHAR(150) | N |  |  |
| data_type | VARCHAR(40) | N |  |  |
| position | INTEGER | N |  |  |
| null_count | INTEGER | N |  |  |
| unique_count | INTEGER | N |  |  |
| min_value | FLOAT | Y |  |  |
| max_value | FLOAT | Y |  |  |
| mean_value | FLOAT | Y |  |  |
| std_value | FLOAT | Y |  |  |
| top_categories | JSON | Y |  |  |
| is_feature | BOOLEAN | N |  |  |
| is_target | BOOLEAN | N |  |  |

### `model_versions`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| name | VARCHAR(150) | N |  |  |
| version | VARCHAR(30) | N | IDX |  |
| algorithm | VARCHAR(40) | N |  |  |
| description | TEXT | Y |  |  |
| dataset_id | INTEGER | Y | FK | -> datasets.id |
| artifact_path | VARCHAR(500) | Y |  |  |
| encoder_path | VARCHAR(500) | Y |  |  |
| scaler_path | VARCHAR(500) | Y |  |  |
| hyperparameters | JSON | Y |  |  |
| feature_names | JSON | Y |  |  |
| feature_importance | JSON | Y |  |  |
| confusion_matrix | JSON | Y |  |  |
| accuracy | FLOAT | Y |  |  |
| precision_score | FLOAT | Y |  |  |
| recall_score | FLOAT | Y |  |  |
| f1_score | FLOAT | Y |  |  |
| roc_auc | FLOAT | Y |  |  |
| cv_mean_score | FLOAT | Y |  |  |
| train_rows | INTEGER | Y |  |  |
| test_rows | INTEGER | Y |  |  |
| training_duration_seconds | FLOAT | Y |  |  |
| status | VARCHAR(40) | N | IDX |  |
| is_active | BOOLEAN | N | IDX |  |
| deployed_at | DATETIME | Y |  |  |
| error_message | TEXT | Y |  |  |
| trained_by_id | INTEGER | Y | FK | -> users.id |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |

### `prediction_batches`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| reference | VARCHAR(50) | N | IDX | unique |
| model_version_id | INTEGER | N | FK | -> model_versions.id |
| source | VARCHAR(40) | N |  |  |
| total_records | INTEGER | N |  |  |
| high_risk_count | INTEGER | N |  |  |
| medium_risk_count | INTEGER | N |  |  |
| low_risk_count | INTEGER | N |  |  |
| average_probability | FLOAT | Y |  |  |
| duration_seconds | FLOAT | Y |  |  |
| triggered_by_id | INTEGER | Y | FK | -> users.id |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |

### `attrition_predictions`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| employee_id | INTEGER | N | FK | -> employees.id |
| model_version_id | INTEGER | N | FK | -> model_versions.id |
| batch_id | INTEGER | Y | FK | -> prediction_batches.id |
| attrition_probability | FLOAT | N | IDX |  |
| will_leave | BOOLEAN | N |  |  |
| risk_level | VARCHAR(40) | N | IDX |  |
| confidence | FLOAT | Y |  |  |
| input_features | JSON | Y |  |  |
| top_factors | JSON | Y |  |  |
| explanation | TEXT | Y |  |  |
| predicted_at | DATETIME | N | IDX |  |
| source | VARCHAR(40) | N |  |  |
| actual_outcome | BOOLEAN | Y |  |  |
| outcome_recorded_at | DATETIME | Y |  |  |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |


## Risk Monitoring

### `risk_scores`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| employee_id | INTEGER | N | FK | -> employees.id |
| prediction_id | INTEGER | Y | FK | -> attrition_predictions.id |
| evaluation_date | DATE | N | IDX |  |
| overall_score | FLOAT | N | IDX |  |
| risk_level | VARCHAR(40) | N | IDX |  |
| trend | VARCHAR(40) | N |  |  |
| previous_score | FLOAT | Y |  |  |
| score_change | FLOAT | Y |  |  |
| ml_probability_score | FLOAT | Y |  |  |
| attendance_score | FLOAT | Y |  |  |
| leave_pattern_score | FLOAT | Y |  |  |
| workload_score | FLOAT | Y |  |  |
| performance_score | FLOAT | Y |  |  |
| compensation_score | FLOAT | Y |  |  |
| tenure_score | FLOAT | Y |  |  |
| engagement_score | FLOAT | Y |  |  |
| breakdown | JSON | Y |  |  |
| summary | TEXT | Y |  |  |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |

### `risk_factors`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| risk_score_id | INTEGER | N | FK | -> risk_scores.id |
| factor_name | VARCHAR(120) | N |  |  |
| factor_category | VARCHAR(60) | Y |  |  |
| contribution | FLOAT | N |  |  |
| current_value | VARCHAR(120) | Y |  |  |
| benchmark_value | VARCHAR(120) | Y |  |  |
| is_negative | BOOLEAN | N |  |  |
| description | TEXT | Y |  |  |

### `risk_alerts`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| employee_id | INTEGER | N | FK | -> employees.id |
| risk_score_id | INTEGER | Y | FK | -> risk_scores.id |
| alert_rule_id | INTEGER | Y | FK | -> alert_rules.id |
| title | VARCHAR(200) | N |  |  |
| message | TEXT | N |  |  |
| risk_level | VARCHAR(40) | N | IDX |  |
| priority | VARCHAR(40) | N |  |  |
| status | VARCHAR(40) | N | IDX |  |
| assigned_to_id | INTEGER | Y | FK | -> users.id |
| acknowledged_by_id | INTEGER | Y | FK | -> users.id |
| acknowledged_at | DATETIME | Y |  |  |
| resolved_at | DATETIME | Y |  |  |
| resolution_notes | TEXT | Y |  |  |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |


## Forecasting

### `workforce_forecasts`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| name | VARCHAR(150) | N |  |  |
| description | TEXT | Y |  |  |
| forecast_type | VARCHAR(40) | N | IDX |  |
| granularity | VARCHAR(40) | N |  |  |
| department_id | INTEGER | Y | FK | -> departments.id |
| period_start | DATE | N |  |  |
| period_end | DATE | N |  |  |
| horizon_periods | INTEGER | N |  |  |
| method | VARCHAR(60) | Y |  |  |
| baseline_value | FLOAT | Y |  |  |
| projected_value | FLOAT | Y |  |  |
| confidence_level | FLOAT | Y |  |  |
| accuracy_mape | FLOAT | Y |  |  |
| assumptions | JSON | Y |  |  |
| generated_by_id | INTEGER | Y | FK | -> users.id |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |

### `forecast_data_points`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| forecast_id | INTEGER | N | FK | -> workforce_forecasts.id |
| period_label | VARCHAR(40) | N |  |  |
| period_date | DATE | N | IDX |  |
| actual_value | FLOAT | Y |  |  |
| predicted_value | FLOAT | N |  |  |
| lower_bound | FLOAT | Y |  |  |
| upper_bound | FLOAT | Y |  |  |
| is_projection | BOOLEAN | N |  |  |

### `forecast_scenarios`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| forecast_id | INTEGER | N | FK | -> workforce_forecasts.id |
| name | VARCHAR(150) | N |  |  |
| description | TEXT | Y |  |  |
| hiring_rate_change | FLOAT | N |  |  |
| attrition_rate_change | FLOAT | N |  |  |
| salary_increase_percent | FLOAT | N |  |  |
| parameters | JSON | Y |  |  |
| projected_headcount | FLOAT | Y |  |  |
| projected_attrition_rate | FLOAT | Y |  |  |
| projected_cost | FLOAT | Y |  |  |
| results | JSON | Y |  |  |
| is_baseline | BOOLEAN | N |  |  |
| created_by_id | INTEGER | Y | FK | -> users.id |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |


## Interventions & Alerts

### `intervention_plans`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| employee_id | INTEGER | N | FK | -> employees.id |
| risk_alert_id | INTEGER | Y | FK | -> risk_alerts.id |
| title | VARCHAR(200) | N |  |  |
| objective | TEXT | Y |  |  |
| intervention_type | VARCHAR(40) | N | IDX |  |
| priority | VARCHAR(40) | N |  |  |
| status | VARCHAR(40) | N | IDX |  |
| risk_score_before | FLOAT | Y |  |  |
| risk_score_after | FLOAT | Y |  |  |
| outcome | VARCHAR(40) | N |  |  |
| outcome_notes | TEXT | Y |  |  |
| estimated_cost | NUMERIC(12, 2) | Y |  |  |
| actual_cost | NUMERIC(12, 2) | Y |  |  |
| start_date | DATE | N |  |  |
| target_end_date | DATE | Y |  |  |
| completed_at | DATETIME | Y |  |  |
| created_by_id | INTEGER | Y | FK | -> users.id |
| owner_id | INTEGER | Y | FK | -> users.id |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |

### `intervention_actions`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| plan_id | INTEGER | N | FK | -> intervention_plans.id |
| title | VARCHAR(200) | N |  |  |
| description | TEXT | Y |  |  |
| assigned_to_id | INTEGER | Y | FK | -> users.id |
| due_date | DATE | Y |  |  |
| is_completed | BOOLEAN | N |  |  |
| completed_at | DATETIME | Y |  |  |
| sequence | INTEGER | N |  |  |
| notes | TEXT | Y |  |  |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |

### `alert_rules`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| name | VARCHAR(150) | N |  |  |
| description | TEXT | Y |  |  |
| metric | VARCHAR(40) | N | IDX |  |
| operator | VARCHAR(40) | N |  |  |
| threshold_value | FLOAT | N |  |  |
| secondary_threshold | FLOAT | Y |  |  |
| scope | VARCHAR(40) | N |  |  |
| department_id | INTEGER | Y | FK | -> departments.id |
| employee_id | INTEGER | Y | FK | -> employees.id |
| priority | VARCHAR(40) | N |  |  |
| channel | VARCHAR(40) | N |  |  |
| notify_roles | JSON | Y |  |  |
| message_template | TEXT | Y |  |  |
| cooldown_hours | INTEGER | N |  |  |
| is_active | BOOLEAN | N | IDX |  |
| trigger_count | INTEGER | N |  |  |
| last_triggered_at | DATETIME | Y |  |  |
| created_by_id | INTEGER | Y | FK | -> users.id |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |

### `alert_triggers`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| rule_id | INTEGER | N | FK | -> alert_rules.id |
| employee_id | INTEGER | Y | FK | -> employees.id |
| department_id | INTEGER | Y | FK | -> departments.id |
| metric_value | FLOAT | N |  |  |
| threshold_value | FLOAT | N |  |  |
| message | TEXT | Y |  |  |
| context | JSON | Y |  |  |
| notifications_sent | INTEGER | N |  |  |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |


## Reports & Audit

### `report_templates`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| name | VARCHAR(150) | N | IDX |  |
| description | TEXT | Y |  |  |
| category | VARCHAR(40) | N | IDX |  |
| default_format | VARCHAR(40) | N |  |  |
| columns | JSON | Y |  |  |
| filters | JSON | Y |  |  |
| grouping | JSON | Y |  |  |
| sort_order | JSON | Y |  |  |
| is_scheduled | BOOLEAN | N |  |  |
| cron_expression | VARCHAR(80) | Y |  |  |
| recipients | JSON | Y |  |  |
| is_system_template | BOOLEAN | N |  |  |
| is_active | BOOLEAN | N |  |  |
| created_by_id | INTEGER | Y | FK | -> users.id |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |

### `generated_reports`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| template_id | INTEGER | Y | FK | -> report_templates.id |
| reference | VARCHAR(50) | N | IDX | unique |
| title | VARCHAR(200) | N |  |  |
| category | VARCHAR(40) | N |  |  |
| file_format | VARCHAR(40) | N |  |  |
| file_path | VARCHAR(500) | Y |  |  |
| file_size | INTEGER | Y |  |  |
| row_count | INTEGER | N |  |  |
| parameters | JSON | Y |  |  |
| status | VARCHAR(40) | N | IDX |  |
| error_message | TEXT | Y |  |  |
| generation_time_seconds | FLOAT | Y |  |  |
| completed_at | DATETIME | Y |  |  |
| expires_at | DATETIME | Y |  |  |
| download_count | INTEGER | N |  |  |
| generated_by_id | INTEGER | Y | FK | -> users.id |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |

### `audit_logs`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| user_id | INTEGER | Y | FK | -> users.id |
| user_email | VARCHAR(255) | Y |  |  |
| user_role | VARCHAR(50) | Y |  |  |
| action | VARCHAR(40) | N | IDX |  |
| entity_type | VARCHAR(80) | N | IDX |  |
| entity_id | INTEGER | Y | IDX |  |
| description | TEXT | Y |  |  |
| old_values | JSON | Y |  |  |
| new_values | JSON | Y |  |  |
| changed_fields | JSON | Y |  |  |
| endpoint | VARCHAR(255) | Y |  |  |
| http_method | VARCHAR(10) | Y |  |  |
| status_code | INTEGER | Y |  |  |
| duration_ms | FLOAT | Y |  |  |
| ip_address | VARCHAR(64) | Y |  |  |
| user_agent | VARCHAR(300) | Y |  |  |
| is_successful | BOOLEAN | N |  |  |
| error_message | TEXT | Y |  |  |
| created_at | DATETIME | N | IDX |  |

### `activity_logs`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| user_id | INTEGER | Y | FK | -> users.id |
| employee_id | INTEGER | Y | FK | -> employees.id |
| activity_type | VARCHAR(60) | N | IDX |  |
| title | VARCHAR(200) | N |  |  |
| description | TEXT | Y |  |  |
| module | VARCHAR(60) | Y | IDX |  |
| reference_type | VARCHAR(60) | Y |  |  |
| reference_id | INTEGER | Y |  |  |
| extra_data | JSON | Y |  |  |
| created_at | DATETIME | N | IDX |  |

### `login_history`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| user_id | INTEGER | Y | FK | -> users.id |
| email_attempted | VARCHAR(255) | N | IDX |  |
| is_successful | BOOLEAN | N | IDX |  |
| failure_reason | VARCHAR(200) | Y |  |  |
| ip_address | VARCHAR(64) | Y |  |  |
| user_agent | VARCHAR(300) | Y |  |  |
| device_type | VARCHAR(50) | Y |  |  |
| location | VARCHAR(150) | Y |  |  |
| logged_in_at | DATETIME | N | IDX |  |
| logged_out_at | DATETIME | Y |  |  |
| session_duration_seconds | FLOAT | Y |  |  |


## Workflow & Tasks

### `workflows`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| name | VARCHAR(150) | N | IDX |  |
| description | TEXT | Y |  |  |
| category | VARCHAR(60) | Y | IDX |  |
| status | VARCHAR(40) | N | IDX |  |
| is_template | BOOLEAN | N |  |  |
| trigger_event | VARCHAR(80) | Y |  |  |
| configuration | JSON | Y |  |  |
| created_by_id | INTEGER | Y | FK | -> users.id |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |
| is_deleted | BOOLEAN | N | IDX |  |
| deleted_at | DATETIME | Y |  |  |

### `workflow_steps`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| workflow_id | INTEGER | N | FK | -> workflows.id |
| name | VARCHAR(150) | N |  |  |
| description | TEXT | Y |  |  |
| sequence | INTEGER | N |  |  |
| assignee_role | VARCHAR(50) | Y |  |  |
| assignee_user_id | INTEGER | Y | FK | -> users.id |
| sla_days | INTEGER | Y |  |  |
| is_mandatory | BOOLEAN | N |  |  |
| requires_approval | BOOLEAN | N |  |  |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |

### `tasks`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| reference | VARCHAR(40) | N | IDX | unique |
| title | VARCHAR(200) | N | IDX |  |
| description | TEXT | Y |  |  |
| workflow_id | INTEGER | Y | FK | -> workflows.id |
| step_id | INTEGER | Y | FK | -> workflow_steps.id |
| parent_task_id | INTEGER | Y | FK | -> tasks.id |
| assigned_to_id | INTEGER | Y | FK | -> users.id |
| assigned_by_id | INTEGER | Y | FK | -> users.id |
| related_employee_id | INTEGER | Y | FK | -> employees.id |
| status | VARCHAR(40) | N | IDX |  |
| priority | VARCHAR(40) | N | IDX |  |
| progress_percent | INTEGER | N |  |  |
| start_date | DATE | Y |  |  |
| due_date | DATE | Y | IDX |  |
| completed_at | DATETIME | Y |  |  |
| estimated_hours | FLOAT | Y |  |  |
| actual_hours | FLOAT | Y |  |  |
| tags | JSON | Y |  |  |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |
| is_deleted | BOOLEAN | N | IDX |  |
| deleted_at | DATETIME | Y |  |  |

### `task_comments`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| task_id | INTEGER | N | FK | -> tasks.id |
| user_id | INTEGER | Y | FK | -> users.id |
| content | TEXT | N |  |  |
| attachment_path | VARCHAR(500) | Y |  |  |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |


## Performance

### `review_cycles`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| name | VARCHAR(120) | N |  | unique |
| description | TEXT | Y |  |  |
| period_start | DATE | N |  |  |
| period_end | DATE | N |  |  |
| self_review_deadline | DATE | Y |  |  |
| manager_review_deadline | DATE | Y |  |  |
| status | VARCHAR(40) | N | IDX |  |
| rating_scale_max | INTEGER | N |  |  |
| competencies | JSON | Y |  |  |
| created_by_id | INTEGER | Y | FK | -> users.id |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |

### `performance_reviews`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| cycle_id | INTEGER | N | FK | -> review_cycles.id |
| employee_id | INTEGER | N | FK | -> employees.id |
| reviewer_id | INTEGER | Y | FK | -> employees.id |
| status | VARCHAR(40) | N | IDX |  |
| self_rating | FLOAT | Y |  |  |
| manager_rating | FLOAT | Y |  |  |
| final_rating | FLOAT | Y | IDX |  |
| competency_ratings | JSON | Y |  |  |
| self_comments | TEXT | Y |  |  |
| manager_comments | TEXT | Y |  |  |
| hr_comments | TEXT | Y |  |  |
| strengths | TEXT | Y |  |  |
| improvement_areas | TEXT | Y |  |  |
| training_recommendations | TEXT | Y |  |  |
| promotion_recommended | BOOLEAN | N |  |  |
| hike_recommended_percent | FLOAT | Y |  |  |
| submitted_at | DATETIME | Y |  |  |
| completed_at | DATETIME | Y |  |  |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |

### `goals`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| employee_id | INTEGER | N | FK | -> employees.id |
| review_id | INTEGER | Y | FK | -> performance_reviews.id |
| title | VARCHAR(200) | N |  |  |
| description | TEXT | Y |  |  |
| category | VARCHAR(60) | Y |  |  |
| metric | VARCHAR(120) | Y |  |  |
| target_value | FLOAT | Y |  |  |
| achieved_value | FLOAT | Y |  |  |
| weight_percent | FLOAT | N |  |  |
| status | VARCHAR(40) | N | IDX |  |
| progress_percent | INTEGER | N |  |  |
| start_date | DATE | Y |  |  |
| due_date | DATE | Y |  |  |
| completed_at | DATETIME | Y |  |  |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |

### `feedbacks`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| from_employee_id | INTEGER | Y | FK | -> employees.id |
| to_employee_id | INTEGER | N | FK | -> employees.id |
| review_id | INTEGER | Y | FK | -> performance_reviews.id |
| feedback_type | VARCHAR(40) | N |  |  |
| content | TEXT | N |  |  |
| rating | FLOAT | Y |  |  |
| is_anonymous | BOOLEAN | N |  |  |
| is_visible_to_employee | BOOLEAN | N |  |  |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |


## AI Recommendations

### `recommendations`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| title | VARCHAR(200) | N |  |  |
| description | TEXT | N |  |  |
| rationale | TEXT | Y |  |  |
| category | VARCHAR(40) | N | IDX |  |
| scope | VARCHAR(40) | N |  |  |
| employee_id | INTEGER | Y | FK | -> employees.id |
| department_id | INTEGER | Y | FK | -> departments.id |
| priority | VARCHAR(40) | N | IDX |  |
| confidence | FLOAT | Y |  |  |
| expected_impact | VARCHAR(200) | Y |  |  |
| estimated_cost | NUMERIC(12, 2) | Y |  |  |
| supporting_data | JSON | Y |  |  |
| status | VARCHAR(40) | N | IDX |  |
| generated_by | VARCHAR(60) | N |  |  |
| model_version_id | INTEGER | Y | FK | -> model_versions.id |
| viewed_at | DATETIME | Y |  |  |
| actioned_at | DATETIME | Y |  |  |
| actioned_by_id | INTEGER | Y | FK | -> users.id |
| expires_at | DATETIME | Y |  |  |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |

### `recommendation_feedbacks`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| recommendation_id | INTEGER | N | FK | -> recommendations.id |
| user_id | INTEGER | Y | FK | -> users.id |
| is_helpful | BOOLEAN | N |  |  |
| rating | INTEGER | Y |  |  |
| comments | TEXT | Y |  |  |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |


## Workforce Stability

### `stability_snapshots`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| snapshot_date | DATE | N | IDX |  |
| scope | VARCHAR(40) | N |  |  |
| department_id | INTEGER | Y | FK | -> departments.id |
| stability_index | FLOAT | N | IDX |  |
| grade | VARCHAR(40) | N | IDX |  |
| trend | VARCHAR(40) | N |  |  |
| previous_index | FLOAT | Y |  |  |
| total_headcount | INTEGER | N |  |  |
| joiners_count | INTEGER | N |  |  |
| exits_count | INTEGER | N |  |  |
| attrition_rate | FLOAT | Y |  |  |
| voluntary_attrition_rate | FLOAT | Y |  |  |
| average_tenure_months | FLOAT | Y |  |  |
| high_risk_count | INTEGER | N |  |  |
| critical_risk_count | INTEGER | N |  |  |
| average_risk_score | FLOAT | Y |  |  |
| average_satisfaction | FLOAT | Y |  |  |
| absence_rate | FLOAT | Y |  |  |
| overtime_ratio | FLOAT | Y |  |  |
| breakdown | JSON | Y |  |  |
| commentary | TEXT | Y |  |  |
| created_at | DATETIME | N |  |  |
| updated_at | DATETIME | N |  |  |

### `stability_metrics`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| id | INTEGER | N | PK |  |
| snapshot_id | INTEGER | N | FK | -> stability_snapshots.id |
| metric_name | VARCHAR(120) | N |  |  |
| metric_category | VARCHAR(60) | Y |  |  |
| value | FLOAT | N |  |  |
| normalised_score | FLOAT | Y |  |  |
| weight | FLOAT | N |  |  |
| benchmark | FLOAT | Y |  |  |
| unit | VARCHAR(30) | Y |  |  |

