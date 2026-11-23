# kliquor — 서울 국산 증류주 영업 기회 분석

공개 데이터만으로 **"국산 증류주가 팔릴 가능성이 높은 서울 상권·업소"**를 추정하고 순위를 매기는 파이프라인입니다.
(현장조사·도매상 데이터 없이 동작. 영업 결과가 쌓이면 가중치를 보정합니다.)

## 1단계 구성 (현재)

| 데이터 | 출처 | 용도 |
|---|---|---|
| 서울 음식 업종 상가 전체 | 공공데이터포털 · 소상공인시장진흥공단 상가(상권)정보 | 업소 목록(업종 소분류·지점명·행정동·좌표) |

```
수집(datagokr) → 표준화·업종 적합도(transform) → 행정동 점수·업소 리드 점수(score) → 리포트(report)
```

**결과물** (`outputs/`)
- `dong_scores.csv` — 행정동별 증류주 기회 점수
- `leads_top.csv` — 상위 업소 리드 (엑셀에서 바로 열림)
- `leads_all.parquet` — 전체 업소 점수
- `summary.md` — 요약 리포트 (규칙에 안 걸린 업종 목록 포함 → 규칙 보완용)

## 점수 방식

- **업종 적합도**: 업종명(중분류+소분류)에 정규식 규칙을 위에서부터 적용 (요리주점 1.0, 횟집 0.95, 고기구이 0.9 … 카페·분식 0)
- **행정동 점수** = 적합 업소 밀집도 · 핵심 업종 비중 · 주점 수 (서울 내 백분위 가중합)
- **업소 점수** = 업종 적합도 × 0.55 + 행정동 점수 × 0.45, 같은 상호 5개 이상이면 프랜차이즈로 보고 절반
- 규칙과 가중치는 모두 `config/scoring.yml`에서 조정합니다. **초기값은 가설입니다.**

## 실행 방법 (GitHub Actions)

### A. 파일데이터(zip) — 권장, 키 불필요
1. [상가(상권)정보 파일데이터](https://www.data.go.kr/data/15083033/fileData.do)에서 최신 zip 다운로드
2. 저장소 **Releases → Draft a new release** → 태그 `data-YYYYMM`(예: `data-202509`) → zip 파일 첨부 → Publish
   (Release 첨부는 2GB까지 가능하고 git 저장소 용량을 차지하지 않음)
3. **Actions → kliquor pipeline → Run workflow** → `mode=csv`, `release_tag=data-202509`
4. 끝나면 실행 요약(Summary)에서 리포트 확인, **Artifacts**에서 CSV 다운로드

> zip 직접 다운로드 URL이 있으면 `csv_url`에 넣어도 됩니다(포털 정책상 막힐 수 있음).

### B. 오픈API — `DATA_GO_KR_API_KEY` 필요
"소상공인시장진흥공단_상가(상권)정보" 오픈API 활용신청 후 `mode=probe` → `mode=all`.

로컬 실행:
```bash
pip install -r requirements.txt
export DATA_GO_KR_API_KEY=...
python -m kliquor.cli ingest --file 소상공인시장진흥공단_상가(상권)정보_202509.zip   # 파일
# 또는
export DATA_GO_KR_API_KEY=... && python -m kliquor.cli all                         # API
```

## 다음 단계

- **서울 열린데이터광장 연동** (키 발급 후): 상권 추정매출(저녁매출·객단가), 인허가(면적·개업일) — 클라이언트와 설정은 `kliquor/seoul_api.py`, `config/sources.yml`의 `seoul:`에 준비됨

- **2단계**: 증류주 취급 신호 — 공개 메뉴·리뷰 텍스트의 키워드를 LLM으로 분류, 경쟁 브랜드가 공개한 취급처 목록 반영
- **3단계**: 영업 결과(연락/성사/실패) 기록 → 가중치 보정 → 단순 예측 모델로 전환
- 지도 시각화 대시보드

## 주의

- 서비스명·컬럼명은 서울시 API 개편으로 바뀔 수 있어 `probe`로 먼저 확인합니다.
- 해외 IP(GitHub 러너)에서 차단되는 경우 self-hosted runner(국내 PC)로 바꿔 실행하세요.
- 네이버 지도·배달앱 등의 대량 크롤링은 약관 및 법적 위험이 있어 사용하지 않습니다.
