"""결과 요약 리포트(markdown) 생성."""
from __future__ import annotations

import pandas as pd


def _table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_(데이터 없음)_\n"
    cols = list(df.columns)
    lines = ["| " + " | ".join(map(str, cols)) + " |", "|" + "---|" * len(cols)]
    for _, row in df.iterrows():
        lines.append("| " + " | ".join("" if pd.isna(v) else str(v) for v in row) + " |")
    return "\n".join(lines) + "\n"


def build_summary(dongs: pd.DataFrame, leads: pd.DataFrame, top_n: int = 20) -> str:
    out = ["# 서울 국산 증류주 영업 기회 리포트\n",
           f"음식 업소 {len(leads):,}곳 · 행정동 {len(dongs):,}곳 · "
           f"프랜차이즈 추정 {int(leads['is_franchise'].sum()):,}곳 · "
           f"핵심 업종(적합도 0.85+) {int((leads['biz_fit'] >= 0.85).sum()):,}곳\n"]

    out.append(f"\n## 행정동 TOP {top_n}\n")
    d = dongs.head(top_n).copy()
    d["핵심업종비중(%)"] = (d["high_fit_share"] * 100).round(0)
    d["적합도합"] = d["fit_density"].round(0)
    out.append(_table(d[["dong_score", "gu", "dong", "stores", "high_fit", "bar_count", "적합도합", "핵심업종비중(%)"]]
                      .rename(columns={"dong_score": "점수", "gu": "구", "dong": "행정동", "stores": "음식업소",
                                       "high_fit": "핵심업종", "bar_count": "주점"})))

    out.append("\n## 자치구 순위 (상위 1,000 리드 기준)\n")
    top = leads.head(1000)
    gu = (top.groupby("gu").agg(리드수=("lead_score", "size"), 평균점수=("lead_score", "mean"))
          .round(1).sort_values("리드수", ascending=False).reset_index().rename(columns={"gu": "구"}))
    out.append(_table(gu))

    out.append("\n## 업종 분포 (상위 1,000 리드)\n")
    out.append(_table(top["category"].value_counts().rename_axis("업종").reset_index(name="리드수").head(20)))

    out.append("\n## 적합도 규칙에 걸리지 않은 업종 (기본값 적용 → 규칙 추가 검토)\n")
    out.append(_table(leads.loc[leads["fit_rule_default"], "category"].value_counts()
                      .rename_axis("업종").reset_index(name="업소수").head(30)))

    out.append(f"\n## 리드 TOP {top_n}\n")
    cols = ["lead_score", "name", "branch", "category", "gu", "dong", "dong_score", "road_address"]
    out.append(_table(leads.head(top_n)[cols]))

    out.append("\n---\n점수는 공개 데이터 기반 **추정치**입니다. 가중치·업종 규칙은 `config/scoring.yml`에서 조정합니다.\n")
    return "\n".join(out)
