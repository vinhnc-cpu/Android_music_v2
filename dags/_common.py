"""Path constants dùng chung cho tất cả DAGs — Airflow bỏ qua file bắt đầu bằng _."""

# Đường dẫn trong Airflow container (dags/ được mount từ ~/airflow/dags/)
PROJECT_PATH = "/opt/airflow/dags/android_music_v2_predict"
MODEL_DIR    = f"{PROJECT_PATH}/models"
