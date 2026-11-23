# kliquor — 서울 국산 증류주 영업 기회 분석

공개 데이터만으로 **"국산 증류주가 팔릴 가능성이 높은 서울 상권·업소"**를 추정하고 순위를 매기는 파이프라인입니다.
(현장조사·도매상 데이터 없이 동작. 영업 결과가 쌓이면 가중치를 보정합니다.)

## 1단계 구성 (현재)

| 데이터 | 출처 | 용도 |
|---|---|---|
| 일반음식점 인허가 | 서울 열린데이터광장 | 업소 목록(업태·면적·개업일·좌표) |
| 상권 추정매출 | 서울시 상권분석서비스 | 저녁매출, 객단가, 30~50대 비중 |
| 상권 영역 | 서울시 상권분석서비스 | 업소 → 상권 매칭 |

```
수집(seoul_api) → 표준화·좌표변환·상권매칭(transform) → 상권 점수·업소 리드 점수(score) → 리포트(report)
```

**결과물** (`outputs/`)
- `district_scores.csv` — 상권별 증류주 기회 점수
- `leads_top.csv` — 상위 업소 리드 (엑셀에서 바로 열림)
- `leads_all.parquet` — 전체 업소 점수
- `summary.md` — 요약 리포트

## 점수 방식

- **상권 점수** = 저녁(17~24시) 매출 · 객단가 · 저녁 비중 · 30~50대 비중 (서울 내 백분위, 가중합)
- **업소 점수** = 업태 적합도 · 상권 점수 · 업태 내 면적 순위 · 신규 개업 가점, 프랜차이즈(동일 브랜드 5개+) 감점
- 모든 가중치와 업태별 적합도는 `config/scoring.yml`에서 조정합니다. **초기값은 가설입니다.**

## 실행 방법 (GitHub Actions)

1. [서울 열린데이터광장](https://data.seoul.go.kr)에서 **일반 인증키** 발급
2. 저장소 **Settings → Secrets and variables → Actions → New repository secret**
   - 이름: `SEOUL_API_KEY`, 값: 발급받은 키
3. **Actions → kliquor pipeline → Run workflow**
   1. `mode=probe` 먼저 실행 → 실행 결과 요약에서 각 API의 실제 컬럼 확인.
      `config/sources.yml`의 서비스명·컬럼명이 다르면 수정합니다.
   2. `mode=all`, `quarter=20252`(최신 공개 분기), `max_rows=2000`으로 시험 실행
   3. 문제 없으면 `max_rows`를 비우고 전체 실행 → **Artifacts**에서 결과 다운로드

로컬 실행:
```bash
pip install -r requirements.txt
export SEOUL_API_KEY=...
python -m kliquor.cli probe
python -m kliquor.cli all --quarter 20252
```

## 다음 단계

- **2단계**: 증류주 취급 신호 — 공개 메뉴·리뷰 텍스트의 키워드를 LLM으로 분류, 경쟁 브랜드가 공개한 취급처 목록 반영
- **3단계**: 영업 결과(연락/성사/실패) 기록 → 가중치 보정 → 단순 예측 모델로 전환
- 지도 시각화 대시보드

## 주의

- 서비스명·컬럼명은 서울시 API 개편으로 바뀔 수 있어 `probe`로 먼저 확인합니다.
- 해외 IP(GitHub 러너)에서 차단되는 경우 self-hosted runner(국내 PC)로 바꿔 실행하세요.
- 네이버 지도·배달앱 등의 대량 크롤링은 약관 및 법적 위험이 있어 사용하지 않습니다.
