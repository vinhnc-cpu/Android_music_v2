"""
DAG: android_music_daily_features

Lịch  : Mỗi ngày lúc 04:00
Flow  : build_training_milestones → build_predict_snapshot → predict

Build training milestones cho install cohort có label window đầy đủ:
  Với mỗi milestone M: install_date = today - M - 7
  → snapshot_date = today - 7, label [today-7, today) đã hoàn chỉnh

Build calendar snapshot cho hôm nay (predict cho user đang active).

Manual trigger:
  airflow dags trigger android_music_daily_features \\
    --conf '{"run_date": "2026-06-15"}'
"""
import logging
import os
import sys
from datetime import date, datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

sys.path.insert(0, "/opt/airflow/dags/android_music_v2_predict")
os.environ.setdefault("MODEL_DIR", "/opt/airflow/dags/android_music_v2_predict/models")

logger = logging.getLogger(__name__)

default_args = {
    "owner":            "ml-team",
    "retries":          1,
    "retry_delay":      timedelta(minutes=15),
    "email_on_failure": False,
}


def _build_training_milestones(**context) -> None:
    """Build milestone snapshots cho install cohort có label window complete.

    Mỗi ngày thêm đúng 5 cohort slices vào training data:
      D1  → users cài today - 1  - 7 = today - 8   (label [today-7, today) complete)
      D7  → users cài today - 7  - 7 = today - 14
      D14 → users cài today - 14 - 7 = today - 21
      D21 → users cài today - 21 - 7 = today - 28
      D28 → users cài today - 28 - 7 = today - 35
    """
    from features.build_feature_store import get_client, build_milestone_snapshot
    from configs.settings import MILESTONES, LABEL_HORIZON

    run_date  = date.fromisoformat(
        (context["dag_run"].conf or {}).get("run_date") or context["ds"]
    )
    client    = get_client()

    for M in MILESTONES:
        install_date = (run_date - timedelta(days=M + LABEL_HORIZON)).isoformat()
        logger.info(f"[dag] training D{M}: install_date={install_date}")
        try:
            build_milestone_snapshot(client, M, install_date, install_date)
        except Exception as e:
            logger.error(f"[dag] D{M} FAILED: {e}")
            raise


def _build_predict_snapshot(**context) -> None:
    """Build calendar snapshot cho hôm nay — dùng để predict."""
    from features.build_feature_store import get_client, build_snapshot

    run_date = (context["dag_run"].conf or {}).get("run_date") or context["ds"]
    logger.info(f"[dag] predict snapshot: {run_date}")
    client = get_client()
    build_snapshot(client, run_date, force=True)


def _predict(**context) -> None:
    from prediction.predict import predict

    run_date = (context["dag_run"].conf or {}).get("run_date") or context["ds"]
    logger.info(f"[dag] predict: {run_date}")
    predict(run_date)


with DAG(
    dag_id="android_music_daily_features",
    description="Daily: training milestones (label-complete) + predict snapshot + predict",
    default_args=default_args,
    schedule_interval="0 4 * * *",
    start_date=datetime(2026, 6, 1),
    catchup=False,
    tags=["android-music", "daily"],
    max_active_runs=1,
) as dag:

    t_train_milestones = PythonOperator(
        task_id="build_training_milestones",
        python_callable=_build_training_milestones,
    )

    t_predict_snap = PythonOperator(
        task_id="build_predict_snapshot",
        python_callable=_build_predict_snapshot,
    )

    t_predict = PythonOperator(
        task_id="predict",
        python_callable=_predict,
    )

    t_train_milestones >> t_predict_snap >> t_predict
