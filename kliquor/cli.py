"""실행 진입점.

  python -m kliquor.cli probe            # 각 API 5건씩 받아 컬럼 확인 → outputs/probe.md
  python -m kliquor.cli collect [--quarter 20252] [--max-rows N]
  python -m kliquor.cli build            # data/raw → outputs/*.csv, summary.md
  python -m kliquor.cli all [--quarter 20252]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd
import yaml

from . import report, score, transform
from .seoul_api import SeoulOpenApi

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "outputs"


def load_cfg() -> tuple[dict, dict]:
    with open(ROOT / "config" / "sources.yml", encoding="utf-8") as f:
        src = yaml.safe_load(f)
    with open(ROOT / "config" / "scoring.yml", encoding="utf-8") as f:
        sc = yaml.safe_load(f)
    return src, sc


def make_client(src: dict) -> SeoulOpenApi:
    return SeoulOpenApi(os.environ.get("SEOUL_API_KEY", ""), src["base_url"],
                        src["page_size"], src["request_sleep_sec"])


def cmd_probe(src: dict) -> None:
    api = make_client(src)
    OUT.mkdir(parents=True, exist_ok=True)
    lines = ["# API probe 결과\n"]
    for key, s in src["sources"].items():
        lines.append(f"## {key} (`{s['service']}`)\n")
        try:
            total, rows = api.fetch_page(s["service"], 1, 5)
            cols = list(rows[0].keys()) if rows else []
            expected = set(s["columns"].values())
            lines.append(f"- 전체 건수: {total:,}")
            lines.append(f"- 응답 컬럼: `{', '.join(cols)}`")
            lines.append(f"- 설정에 있으나 응답에 없는 컬럼: `{sorted(expected - set(cols)) or '없음'}`")
            if rows:
                lines.append(f"- 샘플: `{ {k: rows[0][k] for k in cols[:12]} }`")
        except Exception as exc:  # noqa: BLE001 - probe는 실패도 보고
            lines.append(f"- ❌ 실패: {exc}")
        lines.append("")
    text = "\n".join(lines)
    (OUT / "probe.md").write_text(text, encoding="utf-8")
    print(text)


def cmd_collect(src: dict, quarter: str | None, max_rows: int | None) -> None:
    if not quarter and any(s.get("quarter_param") for s in src["sources"].values()):
        raise SystemExit("--quarter(예: 20252)를 지정하세요. 전체 분기를 받으면 수백만 건이 됩니다.")
    api = make_client(src)
    RAW.mkdir(parents=True, exist_ok=True)
    for key, s in src["sources"].items():
        extra = [quarter] if (s.get("quarter_param") and quarter) else []
        print(f"[collect] {key} ({s['service']}) {extra or ''}", flush=True)
        rows = list(api.iter_rows(s["service"], extra, max_rows))
        df = pd.DataFrame(rows).astype(str)
        df.to_parquet(RAW / f"{key}.parquet", index=False)
        print(f"[collect] {key}: {len(df):,} rows", flush=True)


def cmd_build(src: dict, sc: dict) -> None:
    S = src["sources"]
    raw = {k: pd.read_parquet(RAW / f"{k}.parquet") for k in S}
    rest = transform.build_restaurants(raw["restaurants"], S["restaurants"])
    sales = transform.build_district_sales(raw["district_sales"], S["district_sales"], sc["district_industries"])
    areas = transform.build_district_areas(raw["district_areas"], S["district_areas"])
    rest = transform.match_to_districts(rest, areas, sc["district_match_radius_m"])

    districts = score.score_districts(sales, areas, sc)
    leads = score.score_leads(rest, districts, sc)

    OUT.mkdir(parents=True, exist_ok=True)
    districts.to_csv(OUT / "district_scores.csv", index=False, encoding="utf-8-sig")
    lead_cols = ["lead_score", "name", "biz_type", "gu", "road_address", "lot_address", "area_m2",
                 "license_date", "is_new", "brand", "brand_branches", "is_franchise", "biz_fit",
                 "district_code", "district_score", "lat", "lon", "id"]
    leads.head(sc["top_leads"])[lead_cols].to_csv(OUT / "leads_top.csv", index=False, encoding="utf-8-sig")
    leads[lead_cols].to_parquet(OUT / "leads_all.parquet", index=False)
    summary = report.build_summary(districts, leads)
    (OUT / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="kliquor")
    p.add_argument("command", choices=["probe", "collect", "build", "all"])
    p.add_argument("--quarter", default=None, help="상권 매출 기준 분기 YYYYQ (예: 20252)")
    p.add_argument("--max-rows", type=int, default=None, help="소스별 최대 수집 건수(테스트용)")
    a = p.parse_args(argv)
    src, sc = load_cfg()
    quarter = a.quarter or None
    if a.command == "probe":
        cmd_probe(src)
    if a.command in ("collect", "all"):
        cmd_collect(src, quarter, a.max_rows)
    if a.command in ("build", "all"):
        cmd_build(src, sc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
