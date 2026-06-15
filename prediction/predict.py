"""
Daily uninstall prediction cho Android Music v2.

Cách dùng:
  python -m prediction.predict
  python -m prediction.predict --snapshot_date 2026-06-15
"""
import argparse
import json
import logging
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sklearn.preprocessing import LabelEncoder

from configs.settings import (
    tables, ALL_FEATURES, CATEGORICAL_FEATURES,
    LABEL_COL, MODEL_DIR, LABEL_HORIZON,
)
from features.build_feature_store import get_client, build_snapshot

logger = logging.getLogger(__name__)


def _load_best_model(model_dir) -> str:
    """Đọc model_selection.json để lấy tên model tốt nhất.

    Fallback theo thứ tự lgbm → xgb → catboost nếu file chưa tồn tại.
    """
    sel_path = model_dir / "model_selection.json"
    if sel_path.exists():
        sel = json.loads(sel_path.read_text())
        return sel["best_model"]
    for mtype, ext in [("lgbm", ".txt"), ("xgb", ".json"), ("catboost", ".cbm")]:
        if (model_dir / f"production_{mtype}{ext}").exists():
            return mtype
    raise RuntimeError(f"Không tìm thấy model trong {model_dir}")


_DDL_PREDICTIONS = f"""
CREATE TABLE IF NOT EXISTS {tables.predictions}
(
    prediction_date     Date,
    user_pseudo_id      String,
    uninstall_prob_lgbm Float32 DEFAULT -1,
    uninstall_prob_xgb  Float32 DEFAULT -1,
    uninstall_prob_cb   Float32 DEFAULT -1,
    uninstall_prob_avg  Float32 DEFAULT -1,
    risk_segment        String  DEFAULT '',
    created_at          DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(created_at)
PARTITION BY toYYYYMM(prediction_date)
ORDER BY (prediction_date, user_pseudo_id)
"""


def load_features(client, snap: str) -> pd.DataFrame:
    cols   = ", ".join(["user_pseudo_id"] + ALL_FEATURES)
    result = client.query(
        f"SELECT {cols} FROM {tables.feature_store} FINAL "
        f"WHERE snapshot_date = toDate('{snap}')"
    )
    if not result.result_rows:
        raise ValueError(
            f"Không có features cho {snap}. "
            "Chạy build_feature_store.py --snapshot_date trước."
        )
    df = pd.DataFrame(result.result_rows, columns=result.column_names)
    logger.info(f"[predict] {len(df):,} users loaded for {snap}")
    return df


def encode_for_prediction(df: pd.DataFrame, client, snap: str) -> pd.DataFrame:
    result  = client.query(
        f"SELECT {', '.join(CATEGORICAL_FEATURES)} "
        f"FROM {tables.feature_store} FINAL "
        f"WHERE snapshot_date < toDate('{snap}') "
        f"LIMIT 1000000"
    )
    hist_df = pd.DataFrame(result.result_rows, columns=result.column_names)

    for col in CATEGORICAL_FEATURES:
        if col not in df.columns:
            df[col] = -1
            continue
        le = LabelEncoder()
        known = hist_df[col].fillna("__NA__").astype(str).unique().tolist() if col in hist_df.columns else []
        le.fit(known or ["__NA__"])
        df[col] = df[col].fillna("__NA__").astype(str).map(
            lambda x, le=le: le.transform([x])[0] if x in le.classes_ else -1
        )
    return df


def risk_segment(prob: float) -> str:
    if prob >= 0.7:   return "very_high"
    if prob >= 0.5:   return "high"
    if prob >= 0.3:   return "medium"
    return "low"


def predict(snap: str):
    import lightgbm as lgb
    import xgboost as xgb

    client = get_client()
    client.command(_DDL_PREDICTIONS)

    best_model = _load_best_model(MODEL_DIR)
    logger.info(f"[predict] Selected model: {best_model}")

    # Build features nếu chưa có
    existing = client.query(
        f"SELECT count() FROM {tables.feature_store} FINAL "
        f"WHERE snapshot_date = toDate('{snap}')"
    ).result_rows[0][0]
    if existing == 0:
        logger.info(f"[predict] Building features for {snap}...")
        build_snapshot(client, snap)

    df       = load_features(client, snap)
    user_ids = df["user_pseudo_id"].values
    df       = encode_for_prediction(df, client, snap)
    X        = df[ALL_FEATURES].astype(float)

    preds = {}

    lgbm_path = MODEL_DIR / "production_lgbm.txt"
    if lgbm_path.exists():
        m = lgb.Booster(model_file=str(lgbm_path))
        preds["lgbm"] = m.predict(X)
        logger.info(f"[predict] LGBM mean_prob={preds['lgbm'].mean():.3f}")

    xgb_path = MODEL_DIR / "production_xgb.json"
    if xgb_path.exists():
        m = xgb.Booster()
        m.load_model(str(xgb_path))
        preds["xgb"] = m.predict(xgb.DMatrix(X))
        logger.info(f"[predict] XGB  mean_prob={preds['xgb'].mean():.3f}")

    try:
        from catboost import CatBoostClassifier
        cb_path = MODEL_DIR / "production_catboost.cbm"
        if cb_path.exists():
            m = CatBoostClassifier()
            m.load_model(str(cb_path))
            preds["catboost"] = m.predict_proba(X.values)[:, 1]
            logger.info(f"[predict] CB   mean_prob={preds['catboost'].mean():.3f}")
    except ImportError:
        pass

    if not preds:
        raise RuntimeError("Không tìm thấy model trong " + str(MODEL_DIR))

    # Dùng best model; fallback nếu best không load được
    if best_model not in preds:
        fallback = next(iter(preds))
        logger.warning(f"[predict] {best_model} không có, fallback → {fallback}")
        best_model = fallback
    primary_prob = preds[best_model]
    logger.info(f"[predict] Primary ({best_model}) mean_prob={primary_prob.mean():.3f}")

    result_df = pd.DataFrame({
        "prediction_date":     snap,
        "user_pseudo_id":      user_ids,
        "uninstall_prob_lgbm": preds.get("lgbm",     np.full(len(user_ids), -1.0)),
        "uninstall_prob_xgb":  preds.get("xgb",      np.full(len(user_ids), -1.0)),
        "uninstall_prob_cb":   preds.get("catboost",  np.full(len(user_ids), -1.0)),
        "uninstall_prob_avg":  primary_prob,
        "risk_segment":        [risk_segment(p) for p in primary_prob],
    })

    seg_dist = result_df["risk_segment"].value_counts()
    logger.info(f"[predict] Risk distribution:\n{seg_dist.to_string()}")
    logger.info(
        f"[predict] high+very_high: "
        f"{(primary_prob >= 0.5).sum():,} / {len(primary_prob):,} "
        f"({(primary_prob >= 0.5).mean():.1%})"
    )

    client.insert_df(tables.predictions, result_df)
    logger.info(f"[predict] Inserted {len(result_df):,} rows → {tables.predictions}")
    return result_df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot_date", default=None)
    args = parser.parse_args()

    snap = args.snapshot_date or (date.today() - timedelta(days=1)).isoformat()
    predict(snap)
