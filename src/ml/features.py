"""Turn gold frames into HGB-ready arrays. Unknown categories become missing."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin


class MixedFeatures(BaseEstimator, TransformerMixin):
    def __init__(self, numeric: tuple[str, ...] | list[str], categorical: tuple[str, ...] | list[str]):
        self.numeric = list(numeric)
        self.categorical = list(categorical)

    def fit(self, X, y=None):
        frame = pd.DataFrame(X)
        self.categories_: dict[str, list[str]] = {
            col: sorted(pd.Series(frame[col]).astype("string").fillna("__NA__").unique().tolist())
            for col in self.categorical
        }
        self.n_features_in_ = len(self.numeric) + len(self.categorical)
        self.feature_names_in_ = np.array(self.numeric + self.categorical)
        return self

    def transform(self, X):
        columns = list(self.numeric) + list(self.categorical)
        if isinstance(X, pd.DataFrame):
            frame = X.loc[:, columns]
        else:
            frame = pd.DataFrame(np.asarray(X), columns=columns)
        num = frame[self.numeric].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
        if not self.categorical:
            return num
        cats = []
        for col in self.categorical:
            series = frame[col].astype("string").fillna("__NA__")
            codes = pd.Categorical(series, categories=pd.Index(self.categories_[col])).codes.astype(float)
            codes[codes < 0] = np.nan
            cats.append(codes)
        return np.column_stack([num, np.column_stack(cats)])

    def get_feature_names_out(self, input_features=None):
        return np.array(self.numeric + self.categorical)


def feature_frame(df: pd.DataFrame, numeric: tuple[str, ...], categorical: tuple[str, ...]) -> pd.DataFrame:
    out = df.loc[:, list(numeric) + list(categorical)].copy()
    if "is_shortage_week" in out.columns:
        out["is_shortage_week"] = out["is_shortage_week"].astype(int)
    return out
