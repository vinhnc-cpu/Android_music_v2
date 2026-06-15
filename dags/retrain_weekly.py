"""
DAG: android_music_retrain_weekly

Lịch  : Chủ nhật 03:00
Flow  : build_features_4w → build_risk → train_models → predict

Rebuild features 4 tuần gần nhất (step=7), tính lại risk scores,
train 3 models chọn best, rồi score ngay với model mới.

Manual trigger:
  airflow dags trigger android_music_retrain_weekly \
    --conf '{"snapshot_date": "2026-06-15"}'
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
    "retry_delay":      timedelta(minutes=30),
    "email_on_failure": False,
}


def _build_features_4w(**context) -> None:
    from features.build_feature_store import get_client, build_milestone_snapshot
    from configs.settings import MILESTONES

    snap_to   = (context["dag_run"].conf or {}).get("snapshot_date") or context["ds"]
    snap_from = (date.fromisoformat(snap_to) - timedelta(days=28)).isoformat()

    logger.info(f"[dag] build_features_4w: {snap_from} → {snap_to}, milestones={MILESTONES}")
    client = get_client()
    for milestone in MILESTONES:
        build_milestone_snapshot(client, milestone, snap_from, snap_to)


def _build_risk(**context) -> None:
    from features.build_feature_store import get_client, build_risk_scores

    snap_to   = (context["dag_run"].conf or {}).get("snapshot_date") or context["ds"]
    cutoff    = (date.fromisoformat(snap_to) - timedelta(days=28)).isoformat()
    logger.info(f"[dag] build_risk: cutoff={cutoff}")
    client = get_client()
    build_risk_scores(client, cutoff=cutoff, update_from=cutoff)


def _train_models(**context) -> None:
    from training.train_model import train_model

    logger.info("[dag] train_models: all + shap")
    results = train_model(model_type="all", run_shap_flag=True)
    for mtype, info in results.items():
        m = info["metrics"]
        logger.info(f"  {mtype}: AUC-ROC={m['auc_roc']} AUC-PR={m['auc_pr']} F1={m['f1']}")


def _predict(**context) -> None:
    from prediction.predict import predict

    snap = (context["dag_run"].conf or {}).get("snapshot_date") or context["ds"]
    logger.info(f"[dag] predict: snapshot_date={snap}")
    predict(snap)


with DAG(
    dag_id="android_music_retrain_weekly",
    description="Rebuild features 4 tuần → risk scores → retrain 3 models → predict",
    default_args=default_args,
    schedule_interval="0 3 * * 0",
    start_date=datetime(2026, 6, 1),
    catchup=False,
    tags=["android-music", "train"],
    max_active_runs=1,
) as dag:

    t_features = PythonOperator(
        task_id="build_features_4w",
        python_callable=_build_features_4w,
    )

    t_risk = PythonOperator(
        task_id="build_risk",
        python_callable=_build_risk,
    )

    t_train = PythonOperator(
        task_id="train_models",
        python_callable=_train_models,
    )

    t_predict = PythonOperator(
        task_id="predict",
        python_callable=_predict,
    )

    t_features >> t_risk >> t_train >> t_predict
