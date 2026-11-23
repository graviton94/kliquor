"""원천 데이터 → 표준 테이블 변환, 업소-상권 매칭."""
from __future__ import annotations

import re
import warnings

import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy.spatial import cKDTree

# 미터 단위 공통 좌표계 (Korea 2000 / Central Belt 2010)
WORK_CRS = "EPSG:5186"


def rename_columns(df: pd.DataFrame, mapping: dict[str, str], source: str) -> pd.DataFrame:
    missing = [api for api in mapping.values() if api not in df.columns]
    if missing:
        warnings.warn(f"[{source}] 응답에 없는 컬럼: {missing} — config/sources.yml 확인 필요")
    inv = {api: std for std, api in mapping.items() if api in df.columns}
    out = df[list(inv)].rename(columns=inv)
    for std in mapping:
        if std not in out.columns:
            out[std] = np.nan
    return out


def to_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.replace(",", "").str.strip(), errors="coerce")


def project(df: pd.DataFrame, src_crs: str) -> pd.DataFrame:
    """x, y(원 좌표계) → mx, my(미터, WORK_CRS) 및 lon, lat."""
    df = df.copy()
    x, y = to_num(df["x"]), to_num(df["y"])
    ok = x.notna() & y.notna() & (x != 0) & (y != 0)
    to_work = Transformer.from_crs(src_crs, WORK_CRS, always_xy=True)
    to_wgs = Transformer.from_crs(src_crs, "EPSG:4326", always_xy=True)
    df["mx"] = df["my"] = df["lon"] = df["lat"] = np.nan
    if ok.any():
        mx, my = to_work.transform(x[ok].values, y[ok].values)
        lon, lat = to_wgs.transform(x[ok].values, y[ok].values)
        df.loc[ok, "mx"], df.loc[ok, "my"] = mx, my
        df.loc[ok, "lon"], df.loc[ok, "lat"] = lon, lat
    return df


_BRANCH_RE = re.compile(r"\s*[\(\[]?\s*[^\s\(\)\[\]]+점\s*[\)\]]?\s*$")


def brand_key(name: str) -> str:
    """'봉피양 강남점' → '봉피양'. 지점 접미사를 떼어 브랜드 추정."""
    if not isinstance(name, str):
        return ""
    base = _BRANCH_RE.sub("", name.strip())
    return re.sub(r"\s+", "", base) or re.sub(r"\s+", "", name)


def build_restaurants(raw: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    df = rename_columns(raw, cfg["columns"], "restaurants")
    df["status_code"] = df["status_code"].astype(str).str.strip()
    df = df[df["status_code"].isin(cfg["open_status_codes"])].copy()
    df["biz_type"] = df["biz_type"].fillna("").astype(str).str.strip()
    df["area_m2"] = to_num(df["area_m2"])
    df["license_date"] = pd.to_datetime(
        df["license_date"].astype(str).str.replace("-", "").str[:8], format="%Y%m%d", errors="coerce")
    df["gu"] = (df["road_address"].fillna(df["lot_address"]).astype(str)
                .str.extract(r"서울특별시\s+(\S+구)")[0])
    df["brand"] = df["name"].map(brand_key)
    df = project(df, cfg["crs"])
    return df.reset_index(drop=True)


def build_district_sales(raw: pd.DataFrame, cfg: dict, industries: list[str]) -> pd.DataFrame:
    df = rename_columns(raw, cfg["columns"], "district_sales")
    num_cols = [c for c in df.columns if c.startswith("sales")]
    for c in num_cols:
        df[c] = to_num(df[c]).fillna(0)
    df["quarter"] = df["quarter"].astype(str)
    latest = df["quarter"].max()
    df = df[(df["quarter"] == latest) & df["industry_name"].isin(industries)]
    g = df.groupby(["district_code", "district_name", "quarter"], as_index=False)[num_cols].sum()
    g["district_code"] = g["district_code"].astype(str)
    return g


def build_district_areas(raw: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    df = rename_columns(raw, cfg["columns"], "district_areas")
    df["district_code"] = df["district_code"].astype(str)
    return project(df, cfg["crs"])


def match_to_districts(rest: pd.DataFrame, areas: pd.DataFrame, radius_m: float) -> pd.DataFrame:
    """각 업소를 가장 가까운 상권 중심점(반경 내)에 매칭."""
    rest = rest.copy()
    rest["district_code"] = pd.NA
    rest["district_dist_m"] = np.nan
    a = areas.dropna(subset=["mx", "my"]).reset_index(drop=True)
    has_xy = rest["mx"].notna() & rest["my"].notna()
    if a.empty or not has_xy.any():
        return rest
    tree = cKDTree(a[["mx", "my"]].values)
    dist, idx = tree.query(rest.loc[has_xy, ["mx", "my"]].values, k=1)
    within = dist <= radius_m
    target = rest.index[has_xy][within]
    rest.loc[target, "district_code"] = a.loc[idx[within], "district_code"].values
    rest.loc[rest.index[has_xy], "district_dist_m"] = dist
    return rest
