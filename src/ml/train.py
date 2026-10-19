"""Fit calibrated HistGradientBoosting models on production-honest time splits."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.frozen import FrozenEstimator
from sklearn.inspection import permutation_importance
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline

from src.ml.features import MixedFeatures, feature_frame

RANDOM_STATE = 42


@dataclass
class FittedModel:
    name: str
    pipeline: object
    features: list[str]
    numeric: tuple[str, ...]
    categorical: tuple[str, ...]
    importances: pd.DataFrame
    risk_direction: dict[str, float]
    medians: dict[str, float]
    metrics: dict[str, dict[str, float]]
    calibration_bins: pd.DataFrame
    fairness: pd.DataFrame
    train_n: int
    valid_n: int


def production_honest_attrition(df: pd.DataFrame, as_of: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Train/valid only on snapshots whose 90d label window ends on or before as_of."""
    frame = df.copy()
    frame["snapshot_date"] = pd.to_datetime(frame["snapshot_date"])
    as_of_ts = pd.Timestamp(as_of)
    honest = frame["snapshot_date"] + pd.Timedelta(days=90) <= as_of_ts
    pool = frame.loc[honest].copy()
    snaps = sorted(pool["snapshot_date"].unique())
    if len(snaps) < 4:
        raise ValueError("Need at least four realized snapshots to train and validate.")
    valid_snaps = set(snaps[-2:])
    train = pool.loc[~pool["snapshot_date"].isin(valid_snaps)].copy()
    valid = pool.loc[pool["snapshot_date"].isin(valid_snaps)].copy()
    inference = frame.loc[frame["is_inference_snapshot"].astype(bool)].copy()
    return train, valid, inference


def production_honest_shortage(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Train/valid on weeks with a complete 14d label window; infer the latest week per unit."""
    frame = df.copy()
    frame["week_end"] = pd.to_datetime(frame["week_end"])
    frame["week_start"] = pd.to_datetime(frame["week_start"])
    pool = frame.loc[frame["label_window_complete_14d"].astype(bool)].copy()
    ends = sorted(pool["week_end"].unique())
    if len(ends) < 20:
        raise ValueError("Need at least twenty realized weeks to train and validate.")
    valid_ends = set(ends[-16:])
    train = pool.loc[~pool["week_end"].isin(valid_ends)].copy()
    valid = pool.loc[pool["week_end"].isin(valid_ends)].copy()
    latest = (
        frame.sort_values("week_end")
        .groupby("department_id", as_index=False)
        .tail(1)
        .copy()
    )
    return train, valid, latest


def wrap_calibrated(estimator, X_valid: pd.DataFrame, y_valid: np.ndarray):
    """Sigmoid calibration on the valid split. Skip when a class is too rare for CV."""
    y = np.asarray(y_valid).astype(int)
    minority = int(min((y == 0).sum(), (y == 1).sum()))
    if minority < 2:
        return estimator
    cv = 3 if minority >= 3 else 2
    return CalibratedClassifierCV(FrozenEstimator(estimator), method="sigmoid", cv=cv).fit(X_valid, y)


def _pipeline(numeric: tuple[str, ...], categorical: tuple[str, ...], class_weight: str | None) -> Pipeline:
    n_num = len(numeric)
    cat_idx = list(range(n_num, n_num + len(categorical)))
    clf = HistGradientBoostingClassifier(
        max_depth=2,
        max_iter=80,
        learning_rate=0.06,
        min_samples_leaf=25,
        l2_regularization=1.2,
        random_state=RANDOM_STATE,
        class_weight=class_weight,
        categorical_features=cat_idx,
    )
    return Pipeline(
        [
            ("prep", MixedFeatures(numeric, categorical)),
            ("clf", clf),
        ]
    )


def _proba(model, X: pd.DataFrame) -> np.ndarray:
    return model.predict_proba(X)[:, 1]


def expected_calibration_error(y: np.ndarray, p: np.ndarray, n_bins: int = 8) -> tuple[float, pd.DataFrame]:
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    rows = []
    ece = 0.0
    n = len(y)
    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        mask = (p >= lo) & (p < hi) if i < n_bins - 1 else (p >= lo) & (p <= hi)
        if not mask.any():
            continue
        conf = float(p[mask].mean())
        acc = float(y[mask].mean())
        weight = float(mask.mean())
        ece += weight * abs(acc - conf)
        rows.append(
            {
                "bin": i,
                "lo": lo,
                "hi": hi,
                "n": int(mask.sum()),
                "share": int(mask.sum()) / n,
                "pred_mean": conf,
                "obs_mean": acc,
            }
        )
    if n >= 20 and y.min() != y.max() and p.min() != p.max():
        frac_pos, mean_pred = calibration_curve(y, p, n_bins=min(n_bins, 8), strategy="quantile")
        for i, (obs, pred) in enumerate(zip(frac_pos, mean_pred)):
            if i < len(rows):
                rows[i]["quantile_obs"] = float(obs)
                rows[i]["quantile_pred"] = float(pred)
    return float(ece), pd.DataFrame(rows)


def classification_metrics(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    y = np.asarray(y).astype(int)
    p = np.asarray(p).astype(float)
    out = {
        "n": float(len(y)),
        "n_pos": float(y.sum()),
        "base_rate": float(y.mean()) if len(y) else 0.0,
        "brier": float(brier_score_loss(y, p)) if len(y) else 1.0,
        "mean_p": float(p.mean()) if len(y) else 0.0,
    }
    if len(y) and y.min() != y.max():
        out["roc_auc"] = float(roc_auc_score(y, p))
        out["avg_precision"] = float(average_precision_score(y, p))
    else:
        out["roc_auc"] = float("nan")
        out["avg_precision"] = float("nan")
    ece, _ = expected_calibration_error(y, p)
    out["ece"] = ece
    return out


def slice_metrics(frame: pd.DataFrame, y: np.ndarray, p: np.ndarray, columns: tuple[str, ...], high_risk: np.ndarray) -> pd.DataFrame:
    work = frame.reset_index(drop=True).copy()
    work["_y"] = np.asarray(y).astype(int)
    work["_p"] = np.asarray(p).astype(float)
    work["_hr"] = np.asarray(high_risk).astype(int)
    rows = []
    overall_sel = float(work["_hr"].mean()) if len(work) else 0.0
    for col in columns:
        for value, part in work.groupby(col, dropna=False):
            if len(part) < 8:
                continue
            sel = float(part["_hr"].mean())
            pos = part["_y"] == 1
            rows.append(
                {
                    "slice_column": col,
                    "slice_value": str(value),
                    "n": int(len(part)),
                    "base_rate": float(part["_y"].mean()),
                    "mean_p": float(part["_p"].mean()),
                    "selection_rate": sel,
                    "recall": float(part.loc[pos, "_hr"].mean()) if pos.any() else float("nan"),
                    "selection_ratio_vs_overall": (sel / overall_sel) if overall_sel > 0 else float("nan"),
                    "review_flag": bool(
                        overall_sel > 0 and abs(sel / overall_sel - 1.0) > 0.5 and len(part) >= 15
                    ),
                    "note": "Operational slice, not a protected class. Review with HR; not an automated decision.",
                }
            )
    return pd.DataFrame(rows)


def _high_risk_from_quantile(p: np.ndarray, quantile: float) -> np.ndarray:
    if len(p) == 0:
        return np.array([], dtype=bool)
    cut = float(np.quantile(p, quantile))
    flagged = p >= cut
    # If ties at the cut would flag everyone, keep the top unique scores only.
    if flagged.mean() > (1.0 - quantile) + 0.10:
        order = np.argsort(-p)
        k = max(1, int(round(len(p) * (1.0 - quantile))))
        flagged = np.zeros(len(p), dtype=bool)
        flagged[order[:k]] = True
    return flagged


def fit_model(
    *,
    name: str,
    train: pd.DataFrame,
    valid: pd.DataFrame,
    numeric: tuple[str, ...],
    categorical: tuple[str, ...],
    target: str,
    class_weight: str | None,
    fairness_cols: tuple[str, ...],
    high_risk_quantile: float,
    permutation_repeats: int,
) -> FittedModel:
    X_train = feature_frame(train, numeric, categorical)
    X_valid = feature_frame(valid, numeric, categorical)
    y_train = train[target].astype(int).to_numpy()
    y_valid = valid[target].astype(int).to_numpy()
    pipe = _pipeline(numeric, categorical, class_weight)
    pipe.fit(X_train, y_train)
    calibrated = wrap_calibrated(pipe, X_valid, y_valid)

    p_train = _proba(calibrated, X_train)
    p_valid = _proba(calibrated, X_valid)
    perm = permutation_importance(
        calibrated,
        X_valid,
        y_valid,
        n_repeats=permutation_repeats,
        random_state=RANDOM_STATE,
        scoring="neg_brier_score",
    )
    names = list(numeric) + list(categorical)
    importances = pd.DataFrame(
        {
            "model": name,
            "feature": names,
            "importance_mean": perm.importances_mean,
            "importance_std": perm.importances_std,
        }
    ).sort_values("importance_mean", ascending=False)

    risk_direction: dict[str, float] = {}
    medians: dict[str, float] = {}
    for col in numeric:
        pos = train.loc[train[target] == 1, col]
        neg = train.loc[train[target] == 0, col]
        delta = float(pos.mean() - neg.mean()) if len(pos) and len(neg) else 0.0
        risk_direction[col] = 1.0 if delta >= 0 else -1.0
        medians[col] = float(pd.to_numeric(train[col], errors="coerce").median())

    ece, cal_bins = expected_calibration_error(y_valid, p_valid)
    cal_bins.insert(0, "model", name)
    hr_valid = _high_risk_from_quantile(p_valid, high_risk_quantile)
    fairness = slice_metrics(valid, y_valid, p_valid, fairness_cols, hr_valid)
    if len(fairness):
        fairness.insert(0, "model", name)

    persistence = None
    if name == "shortage" and "is_shortage_week" in valid.columns:
        persist_p = valid["is_shortage_week"].astype(float).to_numpy()
        persistence = classification_metrics(y_valid, persist_p)

    metrics = {
        "train": classification_metrics(y_train, p_train),
        "valid": classification_metrics(y_valid, p_valid),
    }
    metrics["valid"]["ece"] = ece
    if persistence:
        metrics["valid_persistence_baseline"] = persistence

    return FittedModel(
        name=name,
        pipeline=calibrated,
        features=names,
        numeric=numeric,
        categorical=categorical,
        importances=importances,
        risk_direction=risk_direction,
        medians=medians,
        metrics=metrics,
        calibration_bins=cal_bins,
        fairness=fairness if len(fairness) else pd.DataFrame(),
        train_n=len(train),
        valid_n=len(valid),
    )


def local_drivers(
    row: pd.Series,
    importances: pd.DataFrame,
    medians: dict[str, float],
    risk_direction: dict[str, float],
    k: int = 3,
) -> list[str]:
    ranked = []
    for _, rec in importances.iterrows():
        feat = rec["feature"]
        if feat not in medians:
            continue
        value = pd.to_numeric(row.get(feat), errors="coerce")
        if pd.isna(value):
            continue
        scale = abs(medians[feat]) + 1.0
        gap = (float(value) - medians[feat]) * risk_direction.get(feat, 1.0)
        score = float(rec["importance_mean"]) * max(gap, 0.0) / scale
        ranked.append((score, feat, float(value), medians[feat]))
    ranked.sort(reverse=True)
    drivers = []
    for _, feat, value, median in ranked[:k]:
        drivers.append(f"{feat}={value:.2f} vs train median {median:.2f}")
    return drivers
