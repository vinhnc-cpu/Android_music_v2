# Android Music v2 — Uninstall Prediction

Hệ thống dự báo khả năng user gỡ cài đặt app trong 7 ngày tới.

## Cấu trúc

```
Android_Music_v2_Predict/
├── configs/
│   └── settings.py          # ClickHouse config, table names, feature lists
├── features/
│   └── build_feature_store.py  # Tính ~158 features từ flat table
├── training/
│   └── train_model.py       # Train LightGBM + XGBoost + CatBoost
├── prediction/
│   └── predict.py           # Daily scoring
├── models/                  # Model files (.txt / .json / .cbm)
└── docs/
    └── FEATURE_CATALOG.md   # Mô tả đầy đủ 158 features
```

## Thiết lập môi trường

```bash
pip install clickhouse-connect lightgbm xgboost catboost scikit-learn shap mlflow pandas numpy
```

Cấu hình qua biến môi trường (hoặc sửa `configs/settings.py`):
```bash
export CLICKHOUSE_HOST=192.168.1.11
export CLICKHOUSE_PASSWORD=TohGroupData@135
export MLFLOW_TRACKING_URI=http://192.168.1.11:5000
export MODEL_DIR=/path/to/models
```

## Chạy pipeline

### 1. Tạo bảng ClickHouse
```bash
python -m features.build_feature_store --init_tables
```

### 2. Build features (nhiều snapshots)
```bash
python -m features.build_feature_store \
  --date_from 2026-04-14 --date_to 2026-06-08 --step 7
```

### 3. Tính risk scores (target encoding)
```bash
python -m features.build_feature_store \
  --build_risk --risk_cutoff 2026-04-14
```

### 4. Train models
```bash
# Train cả 3 models
python -m training.train_model

# Chỉ train LightGBM + SHAP
python -m training.train_model --model lgbm --shap
```

### 5. Predict hằng ngày
```bash
# Mặc định: hôm qua
python -m prediction.predict

# Ngày cụ thể
python -m prediction.predict --snapshot_date 2026-06-14
```

## Thiết kế kỹ thuật

| Thông số | Giá trị |
|---|---|
| Label | `app_remove` trong [snapshot, snapshot+7d) |
| Label rate | ~25.8% |
| Feature window | 30 ngày trước snapshot |
| Leakage prevention | Mọi feature đều filter `event_date < snapshot_date` |
| Source table | `android_music_v2.android_music_v2_ga4_staging_flat` |
| Feature count | ~158 (26 screens + 33 buttons + các section A–T) |
| Models | LightGBM · XGBoost · CatBoost (ensemble average) |
| Risk segments | very_high (≥0.7) · high (0.5–0.7) · medium (0.3–0.5) · low (<0.3) |

## Kết quả dự báo

Bảng `android_music_v2.music_uninstall_predictions`:

| Cột | Mô tả |
|---|---|
| `prediction_date` | Ngày dự báo |
| `user_pseudo_id` | ID user |
| `uninstall_prob_lgbm/xgb/cb` | Xác suất từng model |
| `uninstall_prob_avg` | Xác suất ensemble |
| `risk_segment` | very_high / high / medium / low |
