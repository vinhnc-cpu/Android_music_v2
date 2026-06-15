#!/usr/bin/env bash
# deploy.sh — Sync project code lên server dùng tar+ssh (không cần rsync).
#
# Cách dùng:
#   bash deploy.sh

set -euo pipefail

SSH_KEY="$HOME/.ssh/id_ed25519_predict"
SERVER="toh@192.168.1.11"
AIRFLOW_DAGS="/home/toh/airflow/dags"
PROJ_DIR="$AIRFLOW_DAGS/android_music_v2_predict"

echo "========================================"
echo " Deploy: Android Music v2 Predict"
echo " Server: $SERVER"
echo " Target: $PROJ_DIR"
echo "========================================"

# ── 1. Tạo thư mục trên server ───────────────────────────────────────────────
echo "[1/3] Creating directories..."
ssh -i "$SSH_KEY" "$SERVER" "mkdir -p $PROJ_DIR/models $PROJ_DIR/logs"

# ── 2. Sync project code qua tar pipe ────────────────────────────────────────
# Dùng tar+ssh thay rsync vì rsync không có sẵn trên Windows Git Bash.
echo "[2/3] Syncing project code (configs, features, training, prediction)..."
tar -czf - \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='*.pyo' \
    --exclude='.env' \
    configs/ features/ training/ prediction/ \
  | ssh -i "$SSH_KEY" "$SERVER" "tar -xzf - -C $PROJ_DIR/"

# ── 3. Copy DAG files vào thư mục dags/ của Airflow ─────────────────────────
echo "[3/3] Copying DAG files..."
scp -i "$SSH_KEY" \
    dags/predict_daily.py \
    dags/retrain_weekly.py \
    "$SERVER:$AIRFLOW_DAGS/"

echo ""
echo "========================================"
echo " Deploy complete!"
echo " DAG files : $AIRFLOW_DAGS/"
echo " Code      : $PROJ_DIR/"
echo " Models    : $PROJ_DIR/models/  (persistent)"
echo ""
echo " Kiểm tra DAGs tại: http://192.168.1.11:8081"
echo "========================================"
