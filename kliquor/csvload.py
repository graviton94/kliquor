"""소상공인시장진흥공단 상가(상권)정보 파일데이터(zip/csv) 적재.

파일 컬럼(한글)을 API 필드명으로 바꿔 data/raw/stores.parquet 로 저장한다.
이후 단계(build)는 API 수집분과 똑같이 동작한다.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pandas as pd

ENCODINGS = ("utf-8-sig", "cp949")


def _read_csv(buf: bytes, usecols_kr: list[str], filters: dict[str, str]) -> pd.DataFrame:
    last_exc: Exception | None = None
    for enc in ENCODINGS:
        try:
            header = pd.read_csv(io.BytesIO(buf), encoding=enc, nrows=0)
            cols = [c for c in header.columns if c.strip() in usecols_kr]
            parts = []
            for chunk in pd.read_csv(io.BytesIO(buf), encoding=enc, usecols=cols, dtype=str,
                                     chunksize=200_000, low_memory=False):
                chunk.columns = [c.strip() for c in chunk.columns]
                for col, val in filters.items():
                    if col in chunk.columns:
                        chunk = chunk[chunk[col].str.strip() == val]
                parts.append(chunk)
            return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=cols)
        except UnicodeDecodeError as exc:
            last_exc = exc
    raise ValueError(f"CSV 인코딩을 읽을 수 없습니다: {last_exc}")


def _members(path: Path, prefer: str) -> list[tuple[str, bytes]]:
    if path.suffix.lower() != ".zip":
        return [(path.name, path.read_bytes())]
    with zipfile.ZipFile(path) as z:
        names = []
        for info in z.infolist():
            name = info.filename
            # 한글 파일명이 cp437로 깨져 들어온 경우 복원
            if not info.flag_bits & 0x800:
                try:
                    name = name.encode("cp437").decode("cp949")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    pass
            if name.lower().endswith(".csv"):
                names.append((name, info.filename))
        preferred = [n for n in names if prefer in n[0]]
        chosen = preferred or names
        return [(disp, z.read(raw)) for disp, raw in chosen]


def load_store_file(path: str | Path, cfg: dict) -> tuple[pd.DataFrame, list[str]]:
    """반환: (API 필드명으로 바뀐 DataFrame, 진행 로그 lines)"""
    path = Path(path)
    std_to_api = cfg["columns"]
    std_to_kr = cfg["csv"]["columns"]
    kr_to_api = {kr: std_to_api[std] for std, kr in std_to_kr.items() if std in std_to_api}
    filters = cfg["csv"]["filters"]
    usecols = sorted(set(std_to_kr.values()) | set(filters))

    log = [f"- 입력 파일: `{path.name}`"]
    frames = []
    for name, buf in _members(path, cfg["csv"]["prefer_member"]):
        df = _read_csv(buf, usecols, filters)
        log.append(f"- `{name}` → 필터 후 {len(df):,}행")
        frames.append(df)
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    missing = sorted(set(std_to_kr.values()) - set(df.columns))
    log.append(f"- 파일에 없는 컬럼: `{missing or '없음'}`")
    df = df.rename(columns=kr_to_api)
    keep = [c for c in kr_to_api.values() if c in df.columns]
    return df[keep].astype(str), log
