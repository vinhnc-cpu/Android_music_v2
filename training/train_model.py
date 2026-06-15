"""
Train Ensemble Uninstall Prediction model cho Android Music v2.

Models: LightGBM + XGBoost + CatBoost
Split  : time-based (80% train / 20% val theo snapshot_date)
Output : models/ + MLflow tracking

Cách dùng:
  python -m training.train_model
  python -m training.train_model --model lgbm
  python -m training.train_model --shap
"""
import argparse
import json
import logging
import warnings
from datetime import date, datetime, timedelta
from typing import List, Tuple

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score, f1_score, precision_score,
    recall_score, roc_auc_score,
)
from sklearn.preprocessing import LabelEncoder

from configs.settings import (
    tables, ALL_FEATURES, CATEGORICAL_FEATURES,
    LABEL_COL, MODEL_DIR, LABEL_HORIZON,
    MLFLOW_URI, MLFLOW_EXPERIMENT, MODEL_SELECTION_METRIC,
)
from features.build_feature_store import get_client

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)

MODEL_DIR.mkdir(parents=True, exist_ok=True)
TRAIN_RATIO = 0.8


# ─────────────────────────────────────────────────────────────────────────────
# Data
# ─────────────────────────────────────────────────────────────────────────────

def load_data(client) -> pd.DataFrame:
    cutoff = (date.today() - timedelta(days=LABEL_HORIZON + 1)).isoformat()
    logger.info(f"[data] Loading feature store (cutoff={cutoff})...")

    cols   = ", ".join(["snapshot_date", "user_pseudo_id"] + ALL_FEATURES + [LABEL_COL])
    result = client.query(
        f"SELECT {cols} FROM {tables.feature_store} FINAL "
        f"WHERE snapshot_date <= toDate('{cutoff}') "
        f"ORDER BY snapshot_date"
    )
    if not result.result_rows:
        raise ValueError("Feature store trống. Chạy build_feature_store.py trước.")

    df = pd.DataFrame(result.result_rows, columns=result.column_names)
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    df = df.drop_duplicates(subset=["snapshot_date", "user_pseudo_id"], keep="last")

    logger.info(
        f"[data] {len(df):,} rows | "
        f"snaps={df['snapshot_date'].nunique()} | "
        f"uninstall_rate={df[LABEL_COL].mean():.1%}"
    )
    return df


def encode_categoricals(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.DataFrame, dict]:
    encoders = {}
    for col in CATEGORICAL_FEATURES:
        if col not in train_df.columns:
            continue
        le = LabelEncoder()
        train_df[col] = le.fit_transform(train_df[col].fillna("__NA__").astype(str))
        val_df[col]   = val_df[col].fillna("__NA__").astype(str).map(
            lambda x, le=le: le.transform([x])[0] if x in le.classes_ else -1
        )
        encoders[col] = le
    return train_df, val_df, encoders


def time_split(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    snaps      = sorted(df["snapshot_date"].unique())
    split_idx  = max(1, int(len(snaps) * TRAIN_RATIO))
    if split_idx >= len(snaps):
        split_idx = len(snaps) - 1
    split_date = snaps[split_idx]
    train = df[df["snapshot_date"] < split_date].copy()
    val   = df[df["snapshot_date"] >= split_date].copy()
    logger.info(
        f"[split] {split_date.date()} | "
        f"train={len(train):,} ({train[LABEL_COL].mean():.1%}) | "
        f"val={len(val):,} ({val[LABEL_COL].mean():.1%})"
    )
    return train, val


def compute_metrics(y_true, y_score, threshold: float = 0.5) -> dict:
    y_pred = (y_score >= threshold).astype(int)
    return {
        "auc_roc":   round(roc_auc_score(y_true, y_score), 4),
        "auc_pr":    round(average_precision_score(y_true, y_score), 4),
        "precision": round(precision_score(y_true, y_pred, zero_division=0), 4),
        "recall":    round(recall_score(y_true, y_pred, zero_division=0), 4),
        "f1":        round(f1_score(y_true, y_pred, zero_division=0), 4),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Model params
# ─────────────────────────────────────────────────────────────────────────────

LGBM_PARAMS = {
    "objective":         "binary",
    "metric":            ["auc", "average_precision"],
    "learning_rate":     0.05,
    "num_leaves":        127,
    "min_child_samples": 200,
    "feature_fraction":  0.8,
    "bagging_fraction":  0.8,
    "bagging_freq":      5,
    "lambda_l1":         0.1,
    "lambda_l2":         0.1,
    "num_threads":       -1,
    "verbose":           -1,
}

XGB_PARAMS = {
    "objective":        "binary:logistic",
    "eval_metric":      "auc",
    "learning_rate":    0.05,
    "max_depth":        6,
    "min_child_weight": 50,
    "subsample":        0.8,
    "colsample_bytree": 0.8,
    "reg_alpha":        0.1,
    "reg_lambda":       0.1,
    "tree_method":      "hist",
    "nthread":          -1,
    "verbosity":        0,
}

CATBOOST_PARAMS = {
    "iterations":    500,
    "learning_rate": 0.05,
    "depth":         7,
    "l2_leaf_reg":   3,
    "eval_metric":   "AUC",
    "verbose":       100,
    "random_seed":   42,
    "task_type":     "CPU",
}


# ─────────────────────────────────────────────────────────────────────────────
# Trainers
# ─────────────────────────────────────────────────────────────────────────────

def train_lgbm(X_train, y_train, X_val, y_val, feature_names: List[str]):
    import lightgbm as lgb
    train_set = lgb.Dataset(X_train, label=y_train, feature_name=feature_names)
    val_set   = lgb.Dataset(X_val,   label=y_val,   reference=train_set)
    model = lgb.train(
        LGBM_PARAMS, train_set,
        num_boost_round=1000,
        valid_sets=[val_set], valid_names=["val"],
        callbacks=[lgb.early_stopping(50), lgb.log_evaluation(100)],
    )
    return model, model.predict(X_val)


def train_xgb(X_train, y_train, X_val, y_val):
    import xgboost as xgb
    dtrain = xgb.DMatrix(X_train, label=y_train)
    dval   = xgb.DMatrix(X_val,   label=y_val)
    model  = xgb.train(
        XGB_PARAMS, dtrain,
        num_boost_round=1000,
        evals=[(dval, "val")],
        early_stopping_rounds=50,
        verbose_eval=100,
    )
    return model, model.predict(dval)


def train_catboost(X_train, y_train, X_val, y_val, cat_indices: List[int]):
    from catboost import CatBoostClassifier
    model = CatBoostClassifier(**CATBOOST_PARAMS, cat_features=cat_indices)
    model.fit(X_train, y_train, eval_set=(X_val, y_val), early_stopping_rounds=50)
    return model, model.predict_proba(X_val)[:, 1]


# ─────────────────────────────────────────────────────────────────────────────
# SHAP
# ─────────────────────────────────────────────────────────────────────────────

def run_shap(model, X_val: pd.DataFrame, model_name: str, run_id: str):
    try:
        import shap
        sample = X_val.sample(min(5000, len(X_val)), random_state=42)
        explainer = shap.TreeExplainer(model)
        sv = explainer.shap_values(sample)
        if isinstance(sv, list):
            sv = sv[1]
        importance = pd.Series(np.abs(sv).mean(axis=0), index=sample.columns)
        importance = importance.sort_values(ascending=False)
        logger.info(f"[shap/{model_name}] Top 20:")
        for i, (f, v) in enumerate(importance.head(20).items(), 1):
            logger.info(f"  {i:2d}. {f:<45} {v:.4f}")
        out = MODEL_DIR / f"shap_{model_name}_{run_id[:8]}.csv"
        importance.to_csv(out, header=["mean_abs_shap"])
        logger.info(f"[shap] Saved → {out}")
        return importance.to_dict()
    except Exception as e:
        logger.warning(f"[shap] Skipped: {e}")
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# Segment analysis
# ─────────────────────────────────────────────────────────────────────────────

def segment_analysis(val_df: pd.DataFrame, preds: np.ndarray):
    df = val_df.copy()
    df["pred"] = preds
    logger.info("\n── Segment Analysis ──")
    for col, bins, labels in [
        ("days_since_install", [0, 1, 3, 7, 30, 9999], ["D0", "D1-3", "D4-7", "D8-30", "D30+"]),
        ("session_cnt_7d",     [0, 1, 3, 7, 99999],    ["0", "1-3", "4-7", "8+"]),
        ("funnel_depth",       [-1, 0, 1, 2, 3, 5],    ["0", "1", "2", "3", "4-5"]),
    ]:
        if col not in df.columns:
            continue
        df["seg"] = pd.cut(df[col], bins=bins, labels=labels, right=True)
        stats = df.groupby("seg", observed=True).agg(
            n=(LABEL_COL, "count"),
            actual=(LABEL_COL, "mean"),
            pred=("pred", "mean"),
        ).round(3)
        logger.info(f"\n{col}:\n{stats.to_string()}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def train_model(model_type: str = "all", run_shap_flag: bool = False):
    import mlflow

    client   = get_client()
    df       = load_data(client)
    train_df, val_df = time_split(df)
    train_df, val_df, encoders = encode_categoricals(train_df, val_df)

    feat_cols   = ALL_FEATURES
    X_train_df  = train_df[feat_cols].astype(float)
    X_val_df    = val_df[feat_cols].astype(float)
    y_train     = train_df[LABEL_COL].astype(int).values
    y_val       = val_df[LABEL_COL].astype(int).values
    X_train     = X_train_df.values
    X_val       = X_val_df.values
    cat_indices = [feat_cols.index(c) for c in CATEGORICAL_FEATURES if c in feat_cols]

    mlflow.set_tracking_uri(MLFLOW_URI)
    mlflow.set_experiment(MLFLOW_EXPERIMENT)

    models_to_train = (
        ["lgbm", "xgb", "catboost"] if model_type == "all" else [model_type]
    )
    results = {}

    for mtype in models_to_train:
        run_name = f"{mtype}_uninstall7d_{datetime.now().strftime('%Y%m%d_%H%M')}"
        with mlflow.start_run(run_name=run_name) as run:
            run_id = run.info.run_id
            logger.info(f"\n{'='*55}\n[{mtype}] run_id={run_id[:8]}\n{'='*55}")

            if mtype == "lgbm":
                model, val_preds = train_lgbm(X_train_df, y_train, X_val_df, y_val, feat_cols)
                params = LGBM_PARAMS
            elif mtype == "xgb":
                model, val_preds = train_xgb(X_train, y_train, X_val, y_val)
                params = XGB_PARAMS
            elif mtype == "catboost":
                model, val_preds = train_catboost(X_train, y_train, X_val, y_val, cat_indices)
                params = CATBOOST_PARAMS

            metrics = compute_metrics(y_val, val_preds)
            mlflow.log_params({**params, "model_type": mtype})
            mlflow.log_metrics(metrics)
            mlflow.log_params({
                "train_rows": len(train_df),
                "val_rows":   len(val_df),
                "n_features": len(feat_cols),
            })

            logger.info(
                f"[{mtype}] AUC-ROC={metrics['auc_roc']} "
                f"AUC-PR={metrics['auc_pr']} "
                f"P={metrics['precision']} R={metrics['recall']} F1={metrics['f1']}"
            )

            # Lưu model + production symlink
            if mtype == "lgbm":
                path = MODEL_DIR / f"uninstall_lgbm_{run_id[:8]}.txt"
                model.save_model(str(path))
                prod = MODEL_DIR / "production_lgbm.txt"
            elif mtype == "xgb":
                path = MODEL_DIR / f"uninstall_xgb_{run_id[:8]}.json"
                model.save_model(str(path))
                prod = MODEL_DIR / "production_xgb.json"
            elif mtype == "catboost":
                path = MODEL_DIR / f"uninstall_catboost_{run_id[:8]}.cbm"
                model.save_model(str(path))
                prod = MODEL_DIR / "production_catboost.cbm"

            if prod.exists() or prod.is_symlink():
                prod.unlink()
            prod.symlink_to(path.name)
            mlflow.log_param("model_path", str(path))
            logger.info(f"[{mtype}] Saved → {path}")

            if run_shap_flag:
                shap_scores = run_shap(model, X_val_df, mtype, run_id)
                if shap_scores:
                    mlflow.log_params({
                        f"shap_{i+1}_{k}": round(v, 4)
                        for i, (k, v) in enumerate(
                            sorted(shap_scores.items(), key=lambda x: -x[1])[:10]
                        )
                    })

            results[mtype] = {"run_id": run_id, "metrics": metrics}

    # Segment analysis
    if "lgbm" in results:
        try:
            import lightgbm as lgb
            m     = lgb.Booster(model_file=str(MODEL_DIR / "production_lgbm.txt"))
            preds = m.predict(X_val_df)
            segment_analysis(val_df, preds)
        except Exception as e:
            logger.warning(f"[segment] Skipped: {e}")

    # ── Model Selection ───────────────────────────────────────────────────────
    if len(results) > 1:
        best = max(results, key=lambda m: results[m]["metrics"][MODEL_SELECTION_METRIC])
        sel  = {
            "best_model":         best,
            "selection_metric":   MODEL_SELECTION_METRIC,
            "trained_at":         datetime.now().isoformat(),
            "metrics_comparison": {m: v["metrics"] for m, v in results.items()},
        }
        sel_path = MODEL_DIR / "model_selection.json"
        sel_path.write_text(json.dumps(sel, indent=2))

        metric_cols = ["AUC-ROC", "AUC-PR", "Precision", "Recall", "F1"]
        metric_keys = ["auc_roc", "auc_pr", "precision", "recall", "f1"]
        sep = "  " + "-" * (13 + 11 * len(metric_cols))
        logger.info("\n── Model Selection ──")
        logger.info("  " + f"{'Model':<13}" + "".join(f"{c:>11}" for c in metric_cols))
        logger.info(sep)
        for m, info in sorted(results.items(),
                               key=lambda x: -x[1]["metrics"][MODEL_SELECTION_METRIC]):
            mtr  = info["metrics"]
            mark = "→" if m == best else " "
            logger.info(
                f"  {mark} {m:<12}" + "".join(f"{mtr[k]:>11.4f}" for k in metric_keys)
            )
        logger.info(sep)
        logger.info(
            f"  Best: {best} "
            f"({MODEL_SELECTION_METRIC}={results[best]['metrics'][MODEL_SELECTION_METRIC]:.4f})"
        )
        logger.info(f"  Saved → {sel_path}")

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="all",
                        choices=["all", "lgbm", "xgb", "catboost"])
    parser.add_argument("--shap", action="store_true")
    args = parser.parse_args()

    results = train_model(args.model, run_shap_flag=args.shap)
    logger.info("\n── Results ──")
    for mtype, info in results.items():
        m = info["metrics"]
        logger.info(
            f"  {mtype:<12} AUC-ROC={m['auc_roc']} "
            f"AUC-PR={m['auc_pr']} F1={m['f1']}"
        )
