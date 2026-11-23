"""상권 점수 · 업소 리드 점수."""
from __future__ import annotations

import numpy as np
import pandas as pd


def pct_rank(s: pd.Series) -> pd.Series:
    return s.rank(pct=True, method="average").fillna(0.0)


def score_districts(sales: pd.DataFrame, areas: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    d = sales.copy()
    d["dinner_sales"] = d["sales_17_21"] + d["sales_21_24"]
    d["avg_ticket"] = np.where(d["sales_cnt"] > 0, d["sales_amt"] / d["sales_cnt"].replace(0, np.nan), np.nan)
    d["dinner_share"] = np.where(d["sales_amt"] > 0, d["dinner_sales"] / d["sales_amt"], np.nan)
    d["age_30_50_share"] = np.where(
        d["sales_amt"] > 0, (d["sales_age30"] + d["sales_age40"] + d["sales_age50"]) / d["sales_amt"], np.nan)

    w = cfg["district_weights"]
    d["district_score"] = sum(pct_rank(d[k]) * v for k, v in w.items()) / sum(w.values())
    d["district_score"] = (d["district_score"] * 100).round(1)

    meta_cols = ["district_code", "district_type", "gu_name", "dong_name", "lon", "lat"]
    meta = areas[[c for c in meta_cols if c in areas.columns]].drop_duplicates("district_code")
    d = d.merge(meta, on="district_code", how="left")
    return d.sort_values("district_score", ascending=False).reset_index(drop=True)


def score_leads(rest: pd.DataFrame, districts: pd.DataFrame, cfg: dict,
                today: pd.Timestamp | None = None) -> pd.DataFrame:
    today = today or pd.Timestamp.today().normalize()
    r = rest.copy()

    fit_map = cfg["biz_type_fit"]
    r["biz_fit"] = r["biz_type"].map(fit_map).fillna(cfg["default_fit"]).astype(float)

    dmap = districts.set_index("district_code")["district_score"]
    # 상권에 속하지 않은 업소는 중간값보다 낮게(0.3) 둔다: 상권 밖 = 유동 적음 가정
    r["district_score"] = r["district_code"].map(dmap)
    r["district_norm"] = (r["district_score"] / 100).fillna(0.3)

    # 면적은 업태 내 백분위 (업태마다 표준 규모가 다름)
    r["size_norm"] = r.groupby("biz_type")["area_m2"].rank(pct=True).fillna(0.5)

    cutoff = today - pd.DateOffset(months=cfg["new_open_months"])
    r["is_new"] = (r["license_date"] >= cutoff).fillna(False)

    branch_counts = r.loc[r["brand"] != "", "brand"].value_counts()
    r["brand_branches"] = r["brand"].map(branch_counts).fillna(1).astype(int)
    r["is_franchise"] = r["brand_branches"] >= cfg["franchise_min_branches"]

    w = cfg["lead_weights"]
    base = (w["biz_fit"] * r["biz_fit"] + w["district"] * r["district_norm"]
            + w["size"] * r["size_norm"] + w["new_open"] * r["is_new"].astype(float)) / sum(w.values())
    base = np.where(r["is_franchise"], base * cfg["franchise_penalty"], base)
    # 적합도 0 업종(카페·김밥 등)은 아예 제외 수준으로
    base = np.where(r["biz_fit"] <= 0, 0, base)
    r["lead_score"] = (base * 100).round(1)
    return r.sort_values("lead_score", ascending=False).reset_index(drop=True)
