"""실행 진입점.

  python -m kliquor.cli probe              # API 5건 받아 컬럼·업종 확인 → outputs/probe.md
  python -m kliquor.cli collect [--max-rows N]
  python -m kliquor.cli build              # data/raw → outputs/*
  python -m kliquor.cli all [--max-rows N]
  python -m kliquor.cli ingest --file 상가정보.zip   # 파일데이터(zip/csv) 적재 (키 불필요)
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd
import yaml

from . import csvload, report, score, transform
from .datagokr import DataGoKrApi

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "outputs"


def load_cfg() -> tuple[dict, dict]:
    with open(ROOT / "config" / "sources.yml", encoding="utf-8") as f:
        src = yaml.safe_load(f)
    with open(ROOT / "config" / "scoring.yml", encoding="utf-8") as f:
        sc = yaml.safe_load(f)
    return src, sc


def make_client(g: dict) -> DataGoKrApi:
    return DataGoKrApi(os.environ.get("DATA_GO_KR_API_KEY", ""), g["base_url"],
                       g["page_size"], g["request_sleep_sec"])


def cmd_probe(src: dict) -> None:
    g = src["datagokr"]
    s = g["stores"]
    OUT.mkdir(parents=True, exist_ok=True)
    lines = ["# API probe 결과\n", f"## stores (`{s['operation']}` {s['params']})\n"]
    try:
        api = make_client(g)
        total, rows = api.fetch_page(s["operation"], s["params"], 1, rows=100)
        cols = list(rows[0].keys()) if rows else []
        lines += [f"- 전체 건수: **{total:,}**",
                  f"- 응답 필드: `{', '.join(cols)}`",
                  f"- 설정에 있으나 응답에 없는 필드: `{sorted(set(s['columns'].values()) - set(cols)) or '없음'}`"]
        if rows:
            df = pd.DataFrame(rows)
            lines.append(f"- 샘플 1건: `{rows[0]}`")
            for c in ["indsMclsNm", "indsSclsNm"]:
                if c in df:
                    lines.append(f"- `{c}` (100건 중): " + ", ".join(
                        f"{k}({v})" for k, v in df[c].value_counts().items()))
    except Exception as exc:  # noqa: BLE001 - probe는 실패도 보고
        lines.append(f"- ❌ 실패: {exc}")
        lines.append("- 확인: 포털에서 '소상공인시장진흥공단_상가(상권)정보' **활용신청**을 했는지, "
                     "승인 후 키가 활성화되기까지(최대 1~2시간) 기다렸는지")
    text = "\n".join(lines) + "\n"
    (OUT / "probe.md").write_text(text, encoding="utf-8")
    print(text)


def cmd_collect(src: dict, max_rows: int | None) -> None:
    g = src["datagokr"]
    s = g["stores"]
    api = make_client(g)
    RAW.mkdir(parents=True, exist_ok=True)
    print(f"[collect] stores {s['params']}", flush=True)
    df = pd.DataFrame(list(api.iter_rows(s["operation"], s["params"], max_rows))).astype(str)
    df.to_parquet(RAW / "stores.parquet", index=False)
    print(f"[collect] stores: {len(df):,} rows", flush=True)


def cmd_ingest(src: dict, file: str) -> None:
    df, log = csvload.load_store_file(file, src["datagokr"]["stores"])
    if df.empty:
        raise SystemExit("적재된 행이 없습니다. outputs/ingest.md 와 config/sources.yml 의 csv 설정을 확인하세요.")
    RAW.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_parquet(RAW / "stores.parquet", index=False)
    lines = ["# 파일 적재 결과\n", *log, f"- 저장: {len(df):,}행\n"]
    for c in ["indsMclsNm", "indsSclsNm"]:
        if c in df:
            lines.append(f"### `{c}` 분포\n")
            lines += [f"- {k}: {v:,}" for k, v in df[c].value_counts().items()]
            lines.append("")
    text = "\n".join(lines) + "\n"
    (OUT / "ingest.md").write_text(text, encoding="utf-8")
    print(text)


def cmd_build(src: dict, sc: dict) -> None:
    raw = pd.read_parquet(RAW / "stores.parquet")
    stores = transform.build_stores(raw, src["datagokr"]["stores"], sc)
    dongs = score.score_dongs(stores, sc)
    leads = score.score_store_leads(stores, dongs, sc)

    OUT.mkdir(parents=True, exist_ok=True)
    dongs.to_csv(OUT / "dong_scores.csv", index=False, encoding="utf-8-sig")
    cols = ["lead_score", "name", "branch", "category", "biz_fit", "gu", "dong", "dong_score",
            "road_address", "lot_address", "building", "floor", "brand_count", "is_franchise",
            "lat", "lon", "id"]
    leads.head(sc["top_leads"])[cols].to_csv(OUT / "leads_top.csv", index=False, encoding="utf-8-sig")
    leads[cols].to_parquet(OUT / "leads_all.parquet", index=False)
    summary = report.build_summary(dongs, leads)
    (OUT / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="kliquor")
    p.add_argument("command", choices=["probe", "collect", "build", "all", "ingest"])
    p.add_argument("--file", default=None, help="ingest: 상가정보 zip 또는 csv 경로")
    p.add_argument("--max-rows", type=int, default=None, help="최대 수집 건수(시험 실행용)")
    a = p.parse_args(argv)
    src, sc = load_cfg()
    if a.command == "ingest":
        if not a.file:
            p.error("ingest 에는 --file 이 필요합니다.")
        cmd_ingest(src, a.file)
        cmd_build(src, sc)
    if a.command == "probe":
        cmd_probe(src)
    if a.command in ("collect", "all"):
        cmd_collect(src, a.max_rows)
    if a.command in ("build", "all"):
        cmd_build(src, sc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
