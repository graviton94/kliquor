"""서울 열린데이터광장 OpenAPI 클라이언트 (페이지네이션 + 재시도)."""
from __future__ import annotations

import time
from typing import Iterator

import requests


class SeoulApiError(RuntimeError):
    pass


NO_DATA_CODE = "INFO-200"


class SeoulOpenApi:
    def __init__(self, api_key: str, base_url: str, page_size: int = 1000,
                 sleep_sec: float = 0.2, timeout: int = 60, retries: int = 4):
        if not api_key:
            raise SeoulApiError("SEOUL_API_KEY가 비어 있습니다.")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.page_size = page_size
        self.sleep_sec = sleep_sec
        self.timeout = timeout
        self.retries = retries
        self.session = requests.Session()

    def _url(self, service: str, start: int, end: int, extra: list[str]) -> str:
        parts = [self.base_url, self.api_key, "json", service, str(start), str(end), *extra]
        return "/".join(parts) + "/"

    def fetch_page(self, service: str, start: int, end: int,
                   extra: list[str] | None = None) -> tuple[int, list[dict]]:
        """(전체 건수, rows) 반환. 데이터 없음이면 (0, [])."""
        url = self._url(service, start, end, extra or [])
        last_exc: Exception | None = None
        for attempt in range(self.retries):
            try:
                resp = self.session.get(url, timeout=self.timeout)
                resp.raise_for_status()
                payload = resp.json()
                return self._parse(service, payload)
            except (requests.RequestException, ValueError) as exc:
                last_exc = exc
                time.sleep(2 ** attempt)
        raise SeoulApiError(f"{service} {start}-{end} 요청 실패: {last_exc}")

    @staticmethod
    def _parse(service: str, payload: dict) -> tuple[int, list[dict]]:
        if service in payload:
            body = payload[service]
            code = body.get("RESULT", {}).get("CODE", "")
            if code and code != "INFO-000":
                if code == NO_DATA_CODE:
                    return 0, []
                raise SeoulApiError(f"{service}: {body.get('RESULT')}")
            return int(body.get("list_total_count", 0)), body.get("row", [])
        result = payload.get("RESULT", {})
        if result.get("CODE") == NO_DATA_CODE:
            return 0, []
        raise SeoulApiError(f"{service}: 예상치 못한 응답 {str(payload)[:300]}")

    def iter_rows(self, service: str, extra: list[str] | None = None,
                  max_rows: int | None = None) -> Iterator[dict]:
        start = 1
        total = None
        fetched = 0
        while True:
            end = start + self.page_size - 1
            if max_rows is not None:
                end = min(end, start + max_rows - fetched - 1)
            total_count, rows = self.fetch_page(service, start, end, extra)
            if total is None:
                total = total_count
            if not rows:
                return
            for row in rows:
                yield row
            fetched += len(rows)
            if (max_rows is not None and fetched >= max_rows) or end >= total:
                return
            start = end + 1
            time.sleep(self.sleep_sec)
