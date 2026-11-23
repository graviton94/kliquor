"""행정동 점수 · 업소 리드 점수."""
from __future__ import annotations

import numpy as np
import pandas as pd


def pct_rank(s: pd.Series) -> pd.Series:
    return s.rank(pct=True, method="average").fillna(0.0)


def score_dongs(stores: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """행정동별 증류주 기회 점수."""
    s = stores.assign(
        is_high=stores["biz_fit"] >= cfg["high_fit_threshold"],
        is_bar=stores["category"].str.contains("주점", na=False)
        & ~stores["category"].str.contains("생맥주|호프|무도|유흥", na=False),
    )
    d = (s.groupby(["dong_code", "gu", "dong"], as_index=False)
         .agg(stores=("id", "size"), fit_density=("biz_fit", "sum"),
              high_fit=("is_high", "sum"), bar_count=("is_bar", "sum"),
              lon=("lon", "mean"), lat=("lat", "mean")))
    d["high_fit_share"] = d["high_fit"] / d["stores"]
    w = cfg["dong_weights"]
    d["dong_score"] = (sum(pct_rank(d[k]) * v for k, v in w.items()) / sum(w.values()) * 100).round(1)
    return d.sort_values("dong_score", ascending=False).reset_index(drop=True)


def score_store_leads(stores: pd.DataFrame, dongs: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    r = stores.copy()
    r["dong_score"] = r["dong_code"].map(dongs.set_index("dong_code")["dong_score"]).fillna(0)

    counts = r.loc[r["brand"] != "", "brand"].value_counts()
    r["brand_count"] = r["brand"].map(counts).fillna(1).astype(int)
    r["is_franchise"] = (r["brand_count"] >= cfg["franchise_min_branches"])

    w = cfg["lead_weights"]
    base = (w["biz_fit"] * r["biz_fit"] + w["dong"] * r["dong_score"] / 100) / sum(w.values())
    base = np.where(r["is_franchise"], base * cfg["franchise_penalty"], base)
    base = np.where(r["biz_fit"] <= 0, 0, base)
    r["lead_score"] = (base * 100).round(1)
    return r.sort_values(["lead_score", "dong_score"], ascending=False).reset_index(drop=True)
