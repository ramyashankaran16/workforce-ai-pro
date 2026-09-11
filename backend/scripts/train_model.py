"""
Train an attrition model from the command line.

    python -m scripts.train_model --source employees
    python -m scripts.train_model --source dataset --dataset-id 1 --algorithm random_forest
    python -m scripts.train_model --source dataset --dataset-id 1 --deploy

Useful for a demo: it prints the metrics table the API returns.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal  # noqa: E402
from app.ml import registry  # noqa: E402
from app.models.enums import ModelAlgorithm  # noqa: E402
from app.services import prediction_service  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Train an attrition model")
    parser.add_argument("--source", choices=["employees", "dataset"], default="employees")
    parser.add_argument("--dataset-id", type=int)
    parser.add_argument(
        "--algorithm",
        choices=[a.value for a in ModelAlgorithm],
        default="gradient_boosting",
    )
    parser.add_argument("--name", default="Attrition Model")
    parser.add_argument("--horizon-days", type=int, default=180)
    parser.add_argument("--target-recall", type=float)
    parser.add_argument("--include-all-exits", action="store_true")
    parser.add_argument("--deploy", action="store_true", help="deploy after training")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        result = prediction_service.train(
            db,
            {
                "name": args.name,
                "algorithm": ModelAlgorithm(args.algorithm),
                "source": args.source,
                "dataset_id": args.dataset_id,
                "horizon_days": args.horizon_days,
                "voluntary_only": not args.include_all_exits,
                "target_recall": args.target_recall,
                "include_protected_attributes": False,
                "test_size": 0.25,
            },
        )

        version = result["model_version"]
        metrics = result["metrics"]

        print(f"\n{version.name} {version.version}  ({version.algorithm.value})")
        print("-" * 58)
        print(f"  rows          train {metrics['train_rows']}, test {metrics['test_rows']}")
        print(f"  positive rate {metrics['positive_rate']:.1%}")
        print()
        print(f"  precision     {metrics['precision']:.3f}")
        print(f"  recall        {metrics['recall']:.3f}")
        print(f"  f1            {metrics['f1']:.3f}")
        print(f"  PR-AUC        {metrics['pr_auc']:.3f}   <- read this, not accuracy")
        print(f"  ROC-AUC       {metrics['roc_auc']}")
        print(f"  accuracy      {metrics['accuracy']:.3f} "
              f"(majority baseline {metrics['baseline_accuracy']:.3f})")
        print(f"  threshold     {metrics['threshold']:.3f} ({metrics['threshold_rule']})")

        matrix = metrics["confusion_matrix"]
        print(f"\n  confusion     TN {matrix['true_negative']}  FP {matrix['false_positive']}")
        print(f"                FN {matrix['false_negative']}  TP {matrix['true_positive']}")

        print("\n  top features")
        for name, weight in list(result["top_features"].items())[:8]:
            bar = "#" * int(weight * 40)
            print(f"    {name:30} {weight:.3f} {bar}")

        print("\n  notes")
        for note in result["notes"]:
            print(f"    - {note}")

        if args.deploy:
            registry.deploy(db, version.id)
            print(f"\n[OK] Deployed {version.name} {version.version}.")
        else:
            print(f"\nDeploy with: POST /api/v1/predictions/models/{version.id}/deploy")
        return 0
    except Exception as exc:
        db.rollback()
        print(f"[FAIL] {type(exc).__name__}: {exc}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
