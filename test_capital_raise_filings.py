"""Company Events 페이지의 "유상증자·자본조달" 공시 섹션 검증 (2026-07-30).

find_capital_raise_filings()가:
(1) 여러 폼타입(S-1/S-3/S-3ASR/424B*) 응답을 하나로 합치면서 같은 accession이 두 폼타입
    질의에 걸쳐 중복 등장해도 한 번만 세는지(dedup)
(2) lookback_days 밖의 오래된 공시는 걸러내는지
(3) 최신순으로 정렬되는지
(4) 반환 dict가 Company Events 카드 형식(headline/source/datetime/url/categories)에
    맞고, URL이 실제 EDGAR 문서 인덱스를 가리키는지
(5) CIK를 못 찾은 티커, 네트워크 실패 상황 모두 예외 없이 조용히 빈 리스트를 반환하는지
(비집계 원칙: "공시 없음"과 "확인 실패"를 구분해 과대 노출하지 않고 둘 다 안전한 빈 결과로
 fail한다 — 자체는 실측 X, 코드가 의도대로 fail-safe인지 검증)
를 실제 SEC를 호출하지 않고 requests.get을 가짜로 갈아끼워 확인한다.
"""
import sys
from datetime import date, timedelta

sys.path.insert(0, "webapp")

from lib._shared_page2_page8_filings import sec_filings

FAKE_CIK = "0001234567"
TODAY = date.today()
RECENT_DATE = (TODAY - timedelta(days=30)).isoformat()
OLD_DATE = (TODAY - timedelta(days=500)).isoformat()  # 365일 lookback 밖
B5_DATE = (TODAY - timedelta(days=5)).isoformat()      # RECENT_DATE보다 더 최신

RECENT_ACCESSION = "0001234567-26-000111"
OLD_ACCESSION = "0001234567-24-000022"
B5_ACCESSION = "0001234567-26-000222"


def _entry(form, fdate, accession):
    return (
        f"<entry><filing-type>{form}</filing-type>"
        f"<filing-date>{fdate}</filing-date>"
        f"<accession-number>{accession}</accession-number></entry>"
    )


def _feed(*entries):
    return "<feed>" + "".join(entries) + "</feed>"


# S-3 질의: 최근 공시 하나 + lookback 밖 오래된 공시 하나
FEED_S3 = _feed(
    _entry("S-3", RECENT_DATE, RECENT_ACCESSION),
    _entry("S-3", OLD_DATE, OLD_ACCESSION),
)
# S-3ASR 질의: 위 최근 공시와 같은 accession이 중복 등장(SEC 쪽 폼타입 접두 매칭 등으로
# 실제로 벌어질 수 있는 상황을 재현) — dedup 검증용
FEED_S3ASR = _feed(_entry("S-3", RECENT_DATE, RECENT_ACCESSION))
# 424B5 질의: 가장 최신 공시 하나(정렬 검증용 — RECENT_DATE보다 나중)
FEED_424B5 = _feed(_entry("424B5", B5_DATE, B5_ACCESSION))
EMPTY_FEED = _feed()

FEEDS_BY_FORM = {
    "S-3": FEED_S3,
    "S-3ASR": FEED_S3ASR,
    "424B5": FEED_424B5,
}

request_log = []


def fake_get(url, **kwargs):
    assert url == "https://www.sec.gov/cgi-bin/browse-edgar", f"엉뚱한 URL 호출: {url}"
    form_type = kwargs["params"]["type"]
    request_log.append(form_type)

    class FakeResponse:
        text = FEEDS_BY_FORM.get(form_type, EMPTY_FEED)

    return FakeResponse()


sec_filings.requests.get = fake_get

# --- 1) 폼타입 8종 모두 질의하는지 -------------------------------------------------
request_log.clear()
filings = sec_filings._list_capital_raise_filings(FAKE_CIK, lookback_days=365)
queried = set(request_log)
assert queried == set(sec_filings._CAPITAL_RAISE_FORMS), \
    f"폼타입 질의 누락: {set(sec_filings._CAPITAL_RAISE_FORMS) - queried}"
print(f"1) 폼타입 {len(queried)}종 전부 질의함: {sorted(queried)}")

# --- 2) dedup + lookback 필터 + 정렬 ------------------------------------------------
accessions = [f["accession"] for f in filings]
assert accessions.count(RECENT_ACCESSION) == 1, \
    f"S-3/S-3ASR 양쪽에 걸친 같은 accession이 중복 집계됨: {accessions}"
assert OLD_ACCESSION not in accessions, "lookback_days 밖 공시가 안 걸러짐"
assert B5_ACCESSION in accessions, "424B5 공시가 누락됨"
assert len(filings) == 2, f"최종 결과 개수가 예상과 다름(2건 기대): {len(filings)}건 — {accessions}"
dates = [f["date"] for f in filings]
assert dates == sorted(dates, reverse=True), f"최신순 정렬이 안 됨: {dates}"
assert filings[0]["accession"] == B5_ACCESSION, "가장 최신(424B5)이 맨 앞이어야 함"
print(f"2) dedup/필터/정렬 OK — {len(filings)}건, 날짜순: {dates}")

# --- 3) find_capital_raise_filings() 반환 형식 --------------------------------------
sec_filings.get_cik = lambda ticker: FAKE_CIK
results = sec_filings.find_capital_raise_filings("FAKE")
assert len(results) == 2, f"개수가 안 맞음: {len(results)}"
top = results[0]
assert top["categories"] == [{"category": "유상증자·자본조달", "matched": ["424B5"]}], \
    f"카테고리 라벨이 안 맞음: {top['categories']}"
assert "424B5" in top["headline"] and "투자설명서" in top["headline"], \
    f"헤드라인에 폼타입/한글 라벨이 없음: {top['headline']!r}"
assert top["source"] == "SEC EDGAR"
expected_url = (
    f"https://www.sec.gov/Archives/edgar/data/{int(FAKE_CIK)}/"
    f"{B5_ACCESSION.replace('-', '')}/{B5_ACCESSION}-index.htm"
)
assert top["url"] == expected_url, f"URL이 안 맞음: {top['url']!r} != {expected_url!r}"
assert isinstance(top["datetime"], int), f"datetime이 epoch(int)가 아님: {top['datetime']!r}"
print(f"3) 반환 형식 OK — headline={top['headline']!r}, url={top['url']}")

# --- 4) CIK를 못 찾은 티커 → 조용히 빈 리스트 ---------------------------------------
sec_filings.get_cik = lambda ticker: None
assert sec_filings.find_capital_raise_filings("NOSUCHTICKER") == []
print("4) CIK 미확인 티커 → [] OK")


# --- 5) 네트워크 실패 → 예외 없이 빈 리스트 -----------------------------------------
def fake_get_broken(url, **kwargs):
    raise ConnectionError("network down")


sec_filings.requests.get = fake_get_broken
sec_filings.get_cik = lambda ticker: FAKE_CIK
assert sec_filings.find_capital_raise_filings("FAKE") == [], "네트워크 실패 시 예외가 새어나감"
print("5) 네트워크 실패 → [] OK (예외 안 새어나감)")

print("\n전부 통과")
