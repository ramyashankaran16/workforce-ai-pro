"""
Generate a realistic workforce for demonstrating the attrition model.

    python -m scripts.generate_demo_data
    python -m scripts.generate_demo_data --count 300 --wipe

Attrition is not assigned at random. Each employee gets a leave probability
built from factors that genuinely drive turnover -- pay below the band median,
long gaps since promotion, heavy overtime, low satisfaction, a long commute,
short tenure. The label is then drawn from that probability, so the signal is
learnable but noisy, which is what real data looks like.

A model that scores 100% on this is overfitting; expect PR-AUC around 0.6-0.8.
"""

import argparse
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, select  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.models.attendance import Attendance  # noqa: E402
from app.models.department import Department, Designation  # noqa: E402
from app.models.employee import Employee, EmployeeHistory  # noqa: E402
from app.models.enums import (  # noqa: E402
    AttendanceStatus,
    EmployeeEventType,
    EmployeeStatus,
    EmploymentType,
    Gender,
    MaritalStatus,
    WorkMode,
)
from app.models.prediction import AttritionPrediction  # noqa: E402
from app.models.risk import RiskScore  # noqa: E402

FIRST_NAMES = [
    "Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Reyansh", "Krishna",
    "Ishaan", "Rohan", "Karthik", "Ananya", "Diya", "Aadhya", "Saanvi",
    "Meera", "Priya", "Kavya", "Riya", "Nithya", "Divya", "Sanjay", "Ramesh",
    "Lakshmi", "Deepa", "Vikram", "Anjali", "Rahul", "Sneha", "Arun", "Pooja",
]
LAST_NAMES = [
    "Sharma", "Verma", "Iyer", "Nair", "Reddy", "Rao", "Menon", "Pillai",
    "Kumar", "Singh", "Patel", "Gupta", "Krishnan", "Subramanian", "Desai",
]
EDUCATION = ["Diploma", "Bachelors", "Masters", "Doctorate"]
TRAVEL = ["None", "Rarely", "Frequently"]
CITIES = ["Salem", "Chennai", "Coimbatore", "Bengaluru", "Madurai", "Hyderabad"]


def leave_probability(profile: dict) -> float:
    """
    Build a plausible probability from real drivers.

    Weights are illustrative, not learned -- the point is to create a signal
    the model can find, not to encode ground truth about attrition.
    """
    score = 0.06  # everyone has some baseline chance

    if profile["salary_percentile"] < 30:
        score += 0.18
    elif profile["salary_percentile"] < 50:
        score += 0.07

    if profile["months_since_promotion"] > 36:
        score += 0.16
    elif profile["months_since_promotion"] > 24:
        score += 0.08

    if profile["satisfaction"] <= 2:
        score += 0.20
    elif profile["satisfaction"] == 3:
        score += 0.05

    if profile["work_life_balance"] <= 2:
        score += 0.12

    if profile["overtime"]:
        score += 0.10

    if profile["commute_km"] > 25:
        score += 0.07

    # the first two years carry the highest risk, then it settles
    if profile["tenure_months"] < 12:
        score += 0.12
    elif profile["tenure_months"] < 24:
        score += 0.06
    elif profile["tenure_months"] > 60:
        score -= 0.05

    if profile["performance"] <= 2:
        score += 0.08
    elif profile["performance"] >= 4.5:
        score += 0.04  # high performers get poached

    if profile["companies_worked"] >= 4:
        score += 0.06

    return max(0.02, min(score, 0.85))


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate demo workforce data")
    parser.add_argument("--count", type=int, default=250)
    parser.add_argument(
        "--wipe", action="store_true",
        help="delete existing generated employees first",
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    db = SessionLocal()

    try:
        departments = db.execute(select(Department)).scalars().all()
        designations = db.execute(select(Designation)).scalars().all()
        if not departments or not designations:
            print("[FAIL] Run: python -m scripts.seed_data first.")
            return 1

        if args.wipe:
            generated = db.execute(
                select(Employee).where(Employee.employee_code.like("DEMO%"))
            ).scalars().all()
            ids = [e.id for e in generated]
            if ids:
                for model in (AttritionPrediction, RiskScore, Attendance, EmployeeHistory):
                    db.execute(delete(model).where(model.employee_id.in_(ids)))
                db.execute(delete(Employee).where(Employee.id.in_(ids)))
                db.commit()
                print(f"  removed {len(ids)} previously generated employee(s)")

        today = date.today()
        band_salaries = {d.id: random.randint(35, 110) * 10000 for d in designations}

        created = 0
        leavers = 0
        managers: list = []

        for index in range(args.count):
            department = random.choice(departments)
            designation = random.choice(designations)

            tenure_months = int(random.triangular(2, 130, 22))
            joined = today - timedelta(days=int(tenure_months * 30.44))

            band = band_salaries[designation.id]
            salary_percentile = random.triangular(5, 95, 50)
            salary = int(band * (0.7 + (salary_percentile / 100) * 0.6))

            months_since_promotion = min(
                tenure_months, int(random.triangular(1, 60, 20))
            )
            satisfaction = random.choices([1, 2, 3, 4, 5], [8, 14, 30, 30, 18])[0]
            balance = random.choices([1, 2, 3, 4, 5], [6, 14, 34, 32, 14])[0]
            environment = random.choices([1, 2, 3, 4, 5], [7, 15, 32, 30, 16])[0]
            performance = round(random.triangular(1.5, 5.0, 3.4), 1)
            overtime = random.random() < 0.32
            commute = round(random.triangular(1, 45, 12), 1)
            companies = random.choices([0, 1, 2, 3, 4, 5], [12, 26, 26, 18, 12, 6])[0]

            profile = {
                "salary_percentile": salary_percentile,
                "months_since_promotion": months_since_promotion,
                "satisfaction": satisfaction,
                "work_life_balance": balance,
                "overtime": overtime,
                "commute_km": commute,
                "tenure_months": tenure_months,
                "performance": performance,
                "companies_worked": companies,
            }

            will_leave = random.random() < leave_probability(profile)

            first = random.choice(FIRST_NAMES)
            last = random.choice(LAST_NAMES)
            code = f"DEMO{index + 1:04d}"

            employee = Employee(
                employee_code=code,
                first_name=first,
                last_name=last,
                work_email=f"{first.lower()}.{last.lower()}{index}@demo.workforce.ai",
                phone=f"+9198{random.randint(10000000, 99999999)}",
                date_of_birth=today - timedelta(days=random.randint(8000, 20000)),
                gender=random.choice(list(Gender)),
                marital_status=random.choice(list(MaritalStatus)),
                city=random.choice(CITIES),
                country="India",
                department_id=department.id,
                designation_id=designation.id,
                employment_type=random.choices(
                    list(EmploymentType), [70, 8, 12, 6, 4]
                )[0],
                work_mode=random.choices(list(WorkMode), [55, 20, 25])[0],
                date_of_joining=joined,
                notice_period_days=random.choice([30, 60, 90]),
                current_salary=salary,
                last_promotion_date=today - timedelta(days=months_since_promotion * 30),
                last_hike_percent=round(random.triangular(0, 25, 8), 1),
                last_hike_date=today - timedelta(days=random.randint(60, 700)),
                total_experience_years=round(tenure_months / 12 + companies * 1.8, 1),
                education_level=random.choice(EDUCATION),
                distance_from_home_km=commute,
                num_companies_worked=companies,
                training_hours_last_year=round(random.triangular(0, 80, 22), 1),
                business_travel_frequency=random.choices(TRAVEL, [45, 40, 15])[0],
                overtime_flag=overtime,
                job_satisfaction_score=satisfaction,
                work_life_balance_score=balance,
                environment_satisfaction_score=environment,
                last_performance_rating=performance,
                status=EmployeeStatus.ACTIVE,
            )

            if will_leave:
                # exit somewhere in the last year of their tenure
                days_ago = random.randint(10, 340)
                exit_date = today - timedelta(days=days_ago)
                if exit_date > joined:
                    employee.date_of_exit = exit_date
                    employee.status = EmployeeStatus.RESIGNED
                    employee.exit_reason = random.choice([
                        "Better compensation elsewhere",
                        "Career growth opportunity",
                        "Relocation",
                        "Work-life balance",
                        "Higher studies",
                        "Manager relationship",
                    ])
                    leavers += 1

            db.add(employee)
            db.flush()

            db.add(
                EmployeeHistory(
                    employee_id=employee.id,
                    event_type=EmployeeEventType.JOINED,
                    effective_date=joined,
                    remarks="Generated demo record",
                )
            )
            if employee.date_of_exit:
                db.add(
                    EmployeeHistory(
                        employee_id=employee.id,
                        event_type=EmployeeEventType.EXIT,
                        effective_date=employee.date_of_exit,
                        field_name="status",
                        new_value="resigned",
                        remarks=employee.exit_reason,
                    )
                )

            if designation.level >= 3 and employee.date_of_exit is None:
                managers.append(employee)
            created += 1

            if created % 50 == 0:
                db.commit()

        db.commit()

        # assign managers, respecting department where possible
        everyone = db.execute(
            select(Employee).where(Employee.employee_code.like("DEMO%"))
        ).scalars().all()
        for employee in everyone:
            if employee in managers:
                continue
            candidates = [
                m for m in managers
                if m.department_id == employee.department_id and m.id != employee.id
            ] or [m for m in managers if m.id != employee.id]
            if candidates:
                employee.manager_id = random.choice(candidates).id
        db.commit()

        # Attendance for the trailing 90 days.
        #
        # Leavers get records too, ending at their exit date. Generating them
        # only for current staff would make "has no attendance data" a perfect
        # predictor of having left -- the model would learn the gap in the data
        # rather than the behaviour behind it.
        print("  generating attendance...")
        for employee in everyone:
            absence_bias = 0.03
            if (employee.job_satisfaction_score or 3) <= 2:
                absence_bias += 0.06
            if employee.overtime_flag:
                absence_bias += 0.02

            for offset in range(90, 0, -1):
                day = today - timedelta(days=offset)
                if day.weekday() >= 5:
                    continue
                if day < employee.date_of_joining:
                    continue
                if employee.date_of_exit and day > employee.date_of_exit:
                    continue
                roll = random.random()
                if roll < absence_bias:
                    status = AttendanceStatus.ABSENT
                    worked = 0.0
                    overtime_hours = 0.0
                elif roll < absence_bias + 0.08:
                    status = AttendanceStatus.LATE
                    worked = round(random.uniform(7.0, 8.5), 2)
                    overtime_hours = 0.0
                else:
                    status = AttendanceStatus.PRESENT
                    worked = round(random.uniform(7.5, 9.5), 2)
                    overtime_hours = (
                        round(max(worked - 8, 0), 2) if employee.overtime_flag else 0.0
                    )

                db.add(
                    Attendance(
                        employee_id=employee.id,
                        attendance_date=day,
                        status=status,
                        worked_hours=worked,
                        overtime_hours=overtime_hours,
                        late_minutes=random.randint(16, 70)
                        if status == AttendanceStatus.LATE else 0,
                    )
                )
            db.commit()

        rate = leavers / created if created else 0
        print(f"\n[OK] Generated {created} employees.")
        print(f"     Leavers: {leavers} ({rate:.1%} attrition rate)")
        print(f"     Managers: {len(managers)}")
        print(f"     Attendance generated for all {len(everyone)} employees")
        print("\nNext:")
        print("  POST /api/v1/predictions/train")
        print("  POST /api/v1/predictions/models/{id}/deploy")
        print("  POST /api/v1/predictions/batch")
        return 0
    except Exception as exc:
        db.rollback()
        print(f"[FAIL] {type(exc).__name__}: {exc}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
