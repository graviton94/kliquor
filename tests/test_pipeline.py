"""네트워크 없이 변환·점수 로직을 검증하는 테스트 (합성 데이터)."""
import pandas as pd
import pytest
import yaml
from pyproj import Transformer

from kliquor import score, transform
from kliquor.cli import ROOT
from kliquor.seoul_api import SeoulOpenApi

SRC = yaml.safe_load((ROOT / "config/sources.yml").read_text(encoding="utf-8"))["sources"]
SC = yaml.safe_load((ROOT / "config/scoring.yml").read_text(encoding="utf-8"))


def _xy(lon, lat, crs):
    return Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform(lon, lat)


def _rest_row(i, name, biz, lon, lat, status="01", area="100", date="20250101"):
    x, y = _xy(lon, lat, SRC["restaurants"]["crs"])
    c = SRC["restaurants"]["columns"]
    return {c["id"]: str(i), c["name"]: name, c["biz_type"]: biz, c["status_code"]: status,
            c["status_name"]: "영업/정상", c["license_date"]: date, c["close_date"]: "",
            c["area_m2"]: area, c["road_address"]: "서울특별시 성동구 성수이로 1",
            c["lot_address"]: "", c["x"]: f"{x:.3f}", c["y"]: f"{y:.3f}"}


@pytest.fixture
def data():
    rest = pd.DataFrame([
        _rest_row(1, "성수 소주방", "정종/대포집/소주방", 127.0560, 37.5445, area="120"),
        _rest_row(2, "카페 라떼", "까페", 127.0561, 37.5446),
        _rest_row(3, "폐업한 한식당", "한식", 127.0562, 37.5447, status="03"),
        _rest_row(4, "멀리 있는 일식", "일식", 126.90, 37.48),
    ] + [_rest_row(10 + i, f"치킨왕 {g}점", "호프/통닭", 127.0563, 37.5448)
         for i, g in enumerate(["강남", "성수", "홍대", "잠실", "신촌"])])

    sc = SRC["district_areas"]["columns"]
    ax, ay = _xy(127.0560, 37.5445, SRC["district_areas"]["crs"])
    bx, by = _xy(126.98, 37.57, SRC["district_areas"]["crs"])
    areas = pd.DataFrame([
        {sc["district_code"]: "A", sc["district_name"]: "성수카페거리", sc["district_type"]: "골목상권",
         sc["gu_name"]: "성동구", sc["dong_name"]: "성수2가1동", sc["x"]: str(ax), sc["y"]: str(ay)},
        {sc["district_code"]: "B", sc["district_name"]: "종로", sc["district_type"]: "발달상권",
         sc["gu_name"]: "종로구", sc["dong_name"]: "종로1가동", sc["x"]: str(bx), sc["y"]: str(by)},
    ])

    ss = SRC["district_sales"]["columns"]
    def sale(code, q, ind, amt, cnt, d1, d2):
        return {ss["quarter"]: q, ss["district_code"]: code, ss["district_name"]: code,
                ss["industry_name"]: ind, ss["sales_amt"]: str(amt), ss["sales_cnt"]: str(cnt),
                ss["sales_17_21"]: str(d1), ss["sales_21_24"]: str(d2), ss["sales_age30"]: str(amt * .3),
                ss["sales_age40"]: str(amt * .2), ss["sales_age50"]: str(amt * .1)}
    sales = pd.DataFrame([
        sale("A", "20252", "한식음식점", 1e9, 20000, 4e8, 2e8),
        sale("A", "20252", "커피-음료", 9e9, 900000, 1e8, 0),     # 제외 업종
        sale("B", "20252", "한식음식점", 5e8, 25000, 1e8, 0),
        sale("A", "20251", "한식음식점", 1, 1, 0, 0),              # 이전 분기 → 제외
    ])
    return rest, areas, sales


def test_end_to_end(data):
    rest_raw, areas_raw, sales_raw = data
    rest = transform.build_restaurants(rest_raw, SRC["restaurants"])
    assert "폐업한 한식당" not in set(rest["name"])
    assert rest["lat"].between(37.4, 37.7).all()

    areas = transform.build_district_areas(areas_raw, SRC["district_areas"])
    sales = transform.build_district_sales(sales_raw, SRC["district_sales"], SC["district_industries"])
    assert len(sales) == 2 and sales.loc[sales.district_code == "A", "sales_amt"].iloc[0] == 1e9

    rest = transform.match_to_districts(rest, areas, SC["district_match_radius_m"])
    assert rest.set_index("name").loc["성수 소주방", "district_code"] == "A"
    assert pd.isna(rest.set_index("name").loc["멀리 있는 일식", "district_code"])

    districts = score.score_districts(sales, areas, SC)
    assert districts.iloc[0]["district_code"] == "A"

    leads = score.score_leads(rest, districts, SC, today=pd.Timestamp("2026-01-01"))
    by = leads.set_index("name")
    assert leads.iloc[0]["name"] == "성수 소주방"
    assert by.loc["카페 라떼", "lead_score"] == 0
    assert by.loc["치킨왕 성수점", "is_franchise"]
    assert by.loc["치킨왕 성수점", "brand"] == "치킨왕"


def test_brand_key():
    assert transform.brand_key("봉피양 강남점") == "봉피양"
    assert transform.brand_key("봉피양(강남점)") == "봉피양"
    assert transform.brand_key("우리집") == "우리집"


def test_api_parse():
    total, rows = SeoulOpenApi._parse("SVC", {"SVC": {"list_total_count": 3,
                                                      "RESULT": {"CODE": "INFO-000"}, "row": [{"a": 1}]}})
    assert total == 3 and rows == [{"a": 1}]
    assert SeoulOpenApi._parse("SVC", {"RESULT": {"CODE": "INFO-200", "MESSAGE": "없음"}}) == (0, [])


def test_report(data):
    from kliquor import report
    rest_raw, areas_raw, sales_raw = data
    areas = transform.build_district_areas(areas_raw, SRC["district_areas"])
    sales = transform.build_district_sales(sales_raw, SRC["district_sales"], SC["district_industries"])
    rest = transform.match_to_districts(transform.build_restaurants(rest_raw, SRC["restaurants"]), areas, 400)
    districts = score.score_districts(sales, areas, SC)
    md = report.build_summary(districts, score.score_leads(rest, districts, SC))
    assert "성수 소주방" in md and "20252" in md
