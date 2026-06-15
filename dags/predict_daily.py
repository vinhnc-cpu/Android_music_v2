"""
DAG: android_music_predict_daily

Lịch  : 02:00 hằng ngày
Flow  : build_features → predict

{{ ds }} trong Airflow = ngày của run (logical date).
Ví dụ: trigger lúc 02:00 ngày 2026-06-16 → ds = 2026-06-15 (hôm qua).

Manual trigger với snapshot_date cụ thể:
  airflow dags trigger android_music_predict_daily \
    --conf '{"snapshot_date": "2026-06-10"}'
"""
import logging
import os
import sys
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

# Thêm project vào sys.path để import configs, features, prediction
sys.path.insert(0, "/opt/airflow/dags/android_music_v2_predict")
os.environ.setdefault("MODEL_DIR", "/opt/airflow/dags/android_music_v2_predict/models")

logger = logging.getLogger(__name__)

default_args = {
    "owner":            "ml-team",
    "retries":          1,
    "retry_delay":      timedelta(minutes=15),
    "email_on_failure": False,
}


def _build_features(**context) -> None:
    from features.build_feature_store import get_client, build_snapshot

    snap   = (context["dag_run"].conf or {}).get("snapshot_date") or context["ds"]
    logger.info(f"[dag] build_features: snapshot_date={snap}")
    client = get_client()
    build_snapshot(client, snap)


def _predict(**context) -> None:
    from prediction.predict import predict

    snap = (context["dag_run"].conf or {}).get("snapshot_date") or context["ds"]
    logger.info(f"[dag] predict: snapshot_date={snap}")
    predict(snap)


with DAG(
    dag_id="android_music_predict_daily",
    description="Build features + score uninstall risk cho hôm qua",
    default_args=default_args,
    schedule_interval="0 2 * * *",
    start_date=datetime(2026, 6, 1),
    catchup=False,
    tags=["android-music", "predict"],
    max_active_runs=1,
) as dag:

    t_build = PythonOperator(
        task_id="build_features",
        python_callable=_build_features,
    )

    t_predict = PythonOperator(
        task_id="predict",
        python_callable=_predict,
    )

    t_build >> t_predict
