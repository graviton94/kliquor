"""네트워크 없이 변환·점수 로직을 검증하는 테스트 (합성 데이터)."""
import pandas as pd
import pytest
import yaml

from kliquor import report, score, transform
from kliquor.cli import ROOT
from kliquor.datagokr import DataGoKrApi, normalize_key
from kliquor.seoul_api import SeoulOpenApi

SRC = yaml.safe_load((ROOT / "config/sources.yml").read_text(encoding="utf-8"))
SC = yaml.safe_load((ROOT / "config/scoring.yml").read_text(encoding="utf-8"))
COLS = SRC["datagokr"]["stores"]["columns"]


def _store(i, name, mcls, scls, dong, branch=""):
    return {COLS["id"]: f"MA{i}", COLS["name"]: name, COLS["branch"]: branch, COLS["lcls"]: "음식",
            COLS["mcls"]: mcls, COLS["scls"]: scls, COLS["gu"]: "성동구" if dong == "성수" else "노원구",
            COLS["dong"]: dong, COLS["dong_code"]: "1" if dong == "성수" else "2",
            COLS["road_address"]: "서울특별시 ...", COLS["lot_address"]: "", COLS["building"]: "",
            COLS["floor"]: "1", COLS["lon"]: "127.05", COLS["lat"]: "37.54"}


@pytest.fixture
def stores_raw():
    rows = [
        _store(1, "성수 술집", "주점", "요리 주점", "성수"),
        _store(2, "성수 횟집", "한식", "횟집", "성수"),
        _store(3, "성수 고기", "한식", "소고기 구이", "성수"),
        _store(4, "라떼하우스", "비알코올", "카페", "성수"),
        _store(5, "상계 분식", "기타 간이", "김밥/만두/분식", "상계"),
        _store(6, "상계 국밥", "한식", "국밥", "상계"),
        _store(7, "알수없음", "기타", "무슨무슨 요리", "상계"),
    ]
    rows += [_store(10 + i, "치킨왕", "기타 간이", "치킨", "상계", branch=f"{g}점")
             for i, g in enumerate(["강남", "성수", "홍대", "잠실", "신촌"])]
    rows.append(_store(1, "성수 술집", "주점", "요리 주점", "성수"))  # 중복
    return pd.DataFrame(rows)


def test_store_pipeline(stores_raw):
    stores = transform.build_stores(stores_raw, SRC["datagokr"]["stores"], SC)
    assert len(stores) == len(stores_raw) - 1
    fit = stores.set_index("name")["biz_fit"]
    assert fit["성수 술집"] == 1.0 and fit["라떼하우스"] == 0.0 and fit["상계 분식"] == 0.0
    assert fit["성수 횟집"] >= 0.9 and fit["알수없음"] == SC["default_fit"]
    assert stores.set_index("name").loc["알수없음", "fit_rule_default"]

    dongs = score.score_dongs(stores, SC)
    assert dongs.iloc[0]["dong"] == "성수"

    leads = score.score_store_leads(stores, dongs, SC)
    assert leads.iloc[0]["name"] == "성수 술집"
    by = leads.drop_duplicates("name").set_index("name")
    assert by.loc["라떼하우스", "lead_score"] == 0
    assert by.loc["치킨왕", "is_franchise"]

    md = report.build_summary(dongs, leads)
    assert "성수 술집" in md and "무슨무슨 요리" in md


def test_fit_rule_order():
    s = pd.Series(["일식 일식 카레/돈가스/덮밥", "일식 일식 회/초밥", "주점 생맥주 전문", "주점 요리 주점"])
    f = transform.category_fit(s, SC["category_fit_rules"], SC["default_fit"]).tolist()
    assert f == [0.3, 0.95, 0.35, 1.0]


def test_brand_key():
    assert transform.brand_key("봉피양 강남점") == "봉피양"
    assert transform.brand_key("봉피양(강남점)") == "봉피양"
    assert transform.brand_key("우리집") == "우리집"


def test_datagokr_parse_and_key():
    ok = {"header": {"resultCode": "00"}, "body": {"totalCount": 2, "items": [{"a": 1}, {"a": 2}]}}
    assert DataGoKrApi._parse(ok) == (2, [{"a": 1}, {"a": 2}])
    assert DataGoKrApi._parse({"header": {"resultCode": "03"}}) == (0, [])
    nested = {"header": {"resultCode": "00"}, "body": {"totalCount": 1, "items": {"item": {"a": 1}}}}
    assert DataGoKrApi._parse(nested) == (1, [{"a": 1}])
    assert normalize_key("abc%2Bdef%3D%3D") == "abc+def=="
    assert normalize_key("abc+def==") == "abc+def=="


def test_seoul_parse():
    total, rows = SeoulOpenApi._parse("SVC", {"SVC": {"list_total_count": 3,
                                                      "RESULT": {"CODE": "INFO-000"}, "row": [{"a": 1}]}})
    assert total == 3 and rows == [{"a": 1}]


def test_csv_zip_ingest(tmp_path):
    import zipfile
    from kliquor import csvload
    kr = SRC["datagokr"]["stores"]["csv"]["columns"]
    cols = list(kr.values()) + ["시도명", "표준산업분류명"]
    def row(i, sido, lcls, scls):
        r = {c: "" for c in cols}
        r.update({kr["id"]: f"MA{i}", kr["name"]: f"가게{i}", kr["lcls"]: lcls, kr["mcls"]: "한식",
                  kr["scls"]: scls, kr["gu"]: "성동구", kr["dong"]: "성수1가1동", kr["dong_code"]: "1120065",
                  kr["lon"]: "127.05", kr["lat"]: "37.54", "시도명": sido})
        return r
    df = pd.DataFrame([row(1, "서울특별시", "음식", "횟집"), row(2, "서울특별시", "소매", "편의점"),
                       row(3, "서울특별시", "음식", "소고기 구이")])
    other = pd.DataFrame([row(9, "부산광역시", "음식", "횟집")])
    zpath = tmp_path / "상가정보.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        z.writestr("소상공인시장진흥공단_상가(상권)정보_서울_202509.csv", df.to_csv(index=False).encode("cp949"))
        z.writestr("소상공인시장진흥공단_상가(상권)정보_부산_202509.csv", other.to_csv(index=False).encode("cp949"))

    out, log = csvload.load_store_file(zpath, SRC["datagokr"]["stores"])
    assert sorted(out["bizesId"]) == ["MA1", "MA3"]
    stores = transform.build_stores(out, SRC["datagokr"]["stores"], SC)
    assert set(stores["biz_fit"]) == {0.95, 0.9}
