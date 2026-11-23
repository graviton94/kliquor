"""결과 요약 리포트(markdown) 생성."""
from __future__ import annotations

import pandas as pd


def _table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_(데이터 없음)_\n"
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, row in df.iterrows():
        lines.append("| " + " | ".join("" if pd.isna(v) else str(v) for v in row) + " |")
    return "\n".join(lines) + "\n"


def build_summary(districts: pd.DataFrame, leads: pd.DataFrame, top_n: int = 20) -> str:
    out = ["# 서울 국산 증류주 영업 기회 리포트\n"]
    if not districts.empty:
        out.append(f"기준 분기: **{districts['quarter'].iloc[0]}** · 상권 {len(districts):,}곳 · "
                   f"영업중 일반음식점 {len(leads):,}곳\n")

    out.append(f"\n## 상권 TOP {top_n}\n")
    d = districts.head(top_n).copy()
    d["저녁매출(억)"] = (d["dinner_sales"] / 1e8).round(1)
    d["객단가(원)"] = d["avg_ticket"].round(-2)
    d["저녁비중"] = (d["dinner_share"] * 100).round(0)
    d["30-50대비중"] = (d["age_30_50_share"] * 100).round(0)
    cols = ["district_score", "gu_name", "district_name", "저녁매출(억)", "객단가(원)", "저녁비중", "30-50대비중"]
    out.append(_table(d[[c for c in cols if c in d.columns]]))

    out.append("\n## 자치구별 상위 리드 분포 (상위 1,000곳)\n")
    top = leads.head(1000)
    gu = (top.groupby("gu").agg(리드수=("lead_score", "size"), 평균점수=("lead_score", "mean"))
          .round(1).sort_values("리드수", ascending=False).reset_index().head(25))
    out.append(_table(gu))

    out.append("\n## 업태별 상위 리드 분포 (상위 1,000곳)\n")
    bt = top["biz_type"].value_counts().rename_axis("업태").reset_index(name="리드수")
    out.append(_table(bt))

    out.append(f"\n## 리드 TOP {top_n}\n")
    cols = ["lead_score", "name", "biz_type", "gu", "district_score", "area_m2", "is_new", "road_address"]
    out.append(_table(leads.head(top_n)[cols]))

    out.append("\n---\n점수는 공개 데이터 기반 **추정치**입니다. 영업 결과를 쌓아 가중치를 보정하세요 "
               "(`config/scoring.yml`).\n")
    return "\n".join(out)
