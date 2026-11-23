"""공공데이터포털(apis.data.go.kr) 클라이언트 — 소상공인시장진흥공단 상가(상권)정보."""
from __future__ import annotations

import time
from typing import Iterator
from urllib.parse import unquote

import requests


class DataGoKrError(RuntimeError):
    pass


NO_DATA_CODES = {"03"}


def normalize_key(key: str) -> str:
    """포털의 '인코딩 키'를 넣어도 동작하도록 디코딩 키로 변환 (requests가 다시 인코딩함)."""
    key = (key or "").strip()
    return unquote(key) if "%" in key else key


class DataGoKrApi:
    def __init__(self, api_key: str, base_url: str, page_size: int = 1000,
                 sleep_sec: float = 0.2, timeout: int = 60, retries: int = 4):
        if not api_key:
            raise DataGoKrError("DATA_GO_KR_API_KEY가 비어 있습니다.")
        self.api_key = normalize_key(api_key)
        self.base_url = base_url.rstrip("/")
        self.page_size = page_size
        self.sleep_sec = sleep_sec
        self.timeout = timeout
        self.retries = retries
        self.session = requests.Session()

    def fetch_page(self, operation: str, params: dict, page: int,
                   rows: int | None = None) -> tuple[int, list[dict]]:
        q = {"serviceKey": self.api_key, "type": "json", "pageNo": page,
             "numOfRows": rows or self.page_size, **params}
        url = f"{self.base_url}/{operation}"
        last_exc: Exception | None = None
        for attempt in range(self.retries):
            try:
                resp = self.session.get(url, params=q, timeout=self.timeout)
                resp.raise_for_status()
                try:
                    payload = resp.json()
                except ValueError:
                    # 키 오류 등은 XML로 옴
                    raise DataGoKrError(f"JSON 아님(키 미등록/활용신청 미승인 가능): {resp.text[:300]}")
                return self._parse(payload)
            except DataGoKrError:
                raise
            except requests.RequestException as exc:
                last_exc = exc
                time.sleep(2 ** attempt)
        raise DataGoKrError(f"{operation} page {page} 요청 실패: {last_exc}")

    @staticmethod
    def _parse(payload: dict) -> tuple[int, list[dict]]:
        header = payload.get("header", {})
        code = str(header.get("resultCode", ""))
        if code in NO_DATA_CODES:
            return 0, []
        if code and code != "00":
            raise DataGoKrError(f"API 오류 {code}: {header.get('resultMsg')}")
        body = payload.get("body", {})
        items = body.get("items", [])
        if isinstance(items, dict):  # {"item": [...]} 형태 대응
            items = items.get("item", [])
        if isinstance(items, dict):
            items = [items]
        return int(body.get("totalCount", 0) or 0), items or []

    def iter_rows(self, operation: str, params: dict,
                  max_rows: int | None = None) -> Iterator[dict]:
        page, fetched = 1, 0
        while True:
            total, rows = self.fetch_page(operation, params, page)
            if not rows:
                return
            for row in rows:
                yield row
                fetched += 1
                if max_rows is not None and fetched >= max_rows:
                    return
            if page * self.page_size >= total:
                return
            if page % 20 == 0:
                print(f"  ... {fetched:,}/{total:,}", flush=True)
            page += 1
            time.sleep(self.sleep_sec)
