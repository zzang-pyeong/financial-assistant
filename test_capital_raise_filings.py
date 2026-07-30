"""Company Events 페이지의 "유상증자·자본조달" 공시 섹션 검증 (2026-07-30, 실제 공모 조건
추출 기능 추가 후 갱신).

find_capital_raise_filings()가:
(1) 여러 폼타입(S-1/S-3/S-3ASR/424B*) 응답을 하나로 합치면서 같은 accession이 두 폼타입
    질의에 걸쳐 중복 등장해도 한 번만 세는지(dedup)
(2) lookback_days 밖의 오래된 공시는 걸러내는지
(3) 최신순으로 정렬되는지
(4) 반환 dict가 Company Events 카드 형식(headline/source/datetime/url/categories)에
    맞고, URL이 실제 EDGAR 문서 인덱스를 가리키는지
(5) CIK를 못 찾은 티커, 네트워크 실패 상황 모두 예외 없이 조용히 빈 리스트를 반환하는지
(6) _extract_offering_detail()이 실측(IREN 2026-07-28 424B5 ATM, INVZ 2026-07-28 424B5
    확정공모)으로 확인한 두 표지 형식에서 실제 조건(한도/주식수·단가·총액)을 뽑는지
(7) find_capital_raise_filings()가 그 조건을 헤드라인에 붙이고, 표지 형식이 안 맞는
    문서는 조건을 지어내지 않고 폼타입만 표시하는지(모르면 모른다)
를 실제 SEC를 호출하지 않고 requests.get을 가짜로 갈아끼워 확인한다.
"""
import sys
from datetime import date, timedelta

sys.path.insert(0, "webapp")

from lib._shared_page2_page8_filings import sec_filings

FAKE_CIK = "0001234567"
CIK_NO_PAD = str(int(FAKE_CIK))
TODAY = date.today()
RECENT_DATE = (TODAY - timedelta(days=30)).isoformat()
OLD_DATE = (TODAY - timedelta(days=500)).isoformat()  # 365일 lookback 밖
B5_DATE = (TODAY - timedelta(days=5)).isoformat()
FIXED_DATE = (TODAY - timedelta(days=2)).isoformat()  # 가장 최신

RECENT_ACCESSION = "0001234567-26-000111"  # 문서를 못 찾는 케이스(폴백 검증용)
OLD_ACCESSION = "0001234567-24-000022"
B5_ACCESSION = "0001234567-26-000222"      # ATM 표지
FIXED_ACCESSION = "0001234567-26-000333"   # 확정공모 표지


def _entry(form, fdate, accession):
    return (
        f"<entry><filing-type>{form}</filing-type>"
        f"<filing-date>{fdate}</filing-date>"
        f"<accession-number>{accession}</accession-number></entry>"
    )


def _feed(*entries):
    return "<feed>" + "".join(entries) + "</feed>"


def _index_url(accession):
    return (
        f"https://www.sec.gov/Archives/edgar/data/{CIK_NO_PAD}/"
        f"{accession.replace('-', '')}/{accession}-index.htm"
    )


def _doc_url(accession, name):
    return f"https://www.sec.gov/Archives/edgar/data/{CIK_NO_PAD}/{accession.replace('-', '')}/{name}"


def _index_table(name, doc_type):
    """_list_filing_documents가 파싱하는 "Document Format Files" 표 형식(td 4개, 3번째
    셀에 href, 4번째 셀에 타입)을 그대로 흉내."""
    return f"<table><tr><td>1</td><td>Prospectus</td><td><a href=\"{name}\">{name}</a></td><td>{doc_type}</td></tr></table>"


# S-3 질의: 최근 공시(RECENT_ACCESSION, 문서 인덱스가 비어 있어 조건 추출 실패 케이스로 씀)
# + lookback 밖 오래된 공시(OLD_ACCESSION, 걸러져야 함)
FEED_S3 = _feed(
    _entry("S-3", RECENT_DATE, RECENT_ACCESSION),
    _entry("S-3", OLD_DATE, OLD_ACCESSION),
)
# S-3ASR 질의: 위 최근 공시와 같은 accession이 중복 등장(SEC 쪽 폼타입 접두 매칭 등으로
# 실제로 벌어질 수 있는 상황을 재현) — dedup 검증용
FEED_S3ASR = _feed(_entry("S-3", RECENT_DATE, RECENT_ACCESSION))
# 424B5 질의: ATM 표지 하나(B5_ACCESSION) + 확정공모 표지 하나(FIXED_ACCESSION, 가장 최신)
FEED_424B5 = _feed(
    _entry("424B5", B5_DATE, B5_ACCESSION),
    _entry("424B5", FIXED_DATE, FIXED_ACCESSION),
)
EMPTY_FEED = _feed()

FEEDS_BY_FORM = {"S-3": FEED_S3, "S-3ASR": FEED_S3ASR, "424B5": FEED_424B5}

# 실측(IREN 2026-07-28 424B5)을 그대로 압축 재현 — 본문에 예전 한도($1,000,000,000)가
# 새 한도($6,000,000,000)보다 먼저 나와도, 표지 맨 앞머리("회사명 Up to $X")만 보고 새
# 한도를 골라야 한다.
ATM_COVER_HTML = (
    "<html><body>IREN Limited Up to $6,000,000,000 Ordinary Shares "
    "We previously entered into an At Market Issuance Sales Agreement... relating to the "
    "offer and sale of our ordinary shares under the sales agreement having an aggregate "
    "offering price of up to $1,000,000,000 and no additional shares will be sold under the "
    "previously filed prospectus. Under this prospectus supplement, we may offer and sell our "
    "ordinary shares having an aggregate offering price of up to $6,000,000,000 from time to "
    "time.</body></html>"
)
# 실측(INVZ 2026-07-28 424B5)을 압축 재현.
FIXED_COVER_HTML = (
    "<html><body>Widget Corp 5,000,000 Ordinary Shares Widget Corp is offering 5,000,000 "
    "ordinary shares. Per Ordinary Share Total Offering price $ 10.00 $ 50,000,000.00 "
    "Placement agent fees $ 0.60 $ 3,000,000.00</body></html>"
)

INDEX_PAGES = {
    _index_url(RECENT_ACCESSION): "<html><body>no document table here</body></html>",
    _index_url(B5_ACCESSION): _index_table("atm424b5.htm", "424B5"),
    _index_url(FIXED_ACCESSION): _index_table("fixed424b5.htm", "424B5"),
}
DOC_PAGES = {
    _doc_url(B5_ACCESSION, "atm424b5.htm"): ATM_COVER_HTML,
    _doc_url(FIXED_ACCESSION, "fixed424b5.htm"): FIXED_COVER_HTML,
}

request_log = []


def fake_get(url, **kwargs):
    if url == "https://www.sec.gov/cgi-bin/browse-edgar":
        form_type = kwargs["params"]["type"]
        request_log.append(form_type)

        class R:
            text = FEEDS_BY_FORM.get(form_type, EMPTY_FEED)
        return R()
    if url in INDEX_PAGES:
        class R:
            text = INDEX_PAGES[url]
        return R()
    if url in DOC_PAGES:
        class R:
            text = DOC_PAGES[url]
        return R()
    raise AssertionError(f"예상 못 한 URL 호출: {url}")


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
assert set(accessions) == {RECENT_ACCESSION, B5_ACCESSION, FIXED_ACCESSION}, \
    f"최종 결과 구성이 예상과 다름: {accessions}"
dates = [f["date"] for f in filings]
assert dates == sorted(dates, reverse=True), f"최신순 정렬이 안 됨: {dates}"
assert accessions[0] == FIXED_ACCESSION, "가장 최신(FIXED_ACCESSION)이 맨 앞이어야 함"
print(f"2) dedup/필터/정렬 OK — {len(filings)}건, 날짜순: {dates}")

# --- 3) _extract_offering_detail() 단독 검증(실측 표지 형식 2종) ----------------------
atm_detail = sec_filings._extract_offering_detail(ATM_COVER_HTML)
assert atm_detail == "최대 $6,000,000,000 규모 시장가매도(ATM)·Shelf 한도", \
    f"ATM 한도를 잘못 뽑음(예전 한도를 골랐을 가능성): {atm_detail!r}"
fixed_detail = sec_filings._extract_offering_detail(FIXED_COVER_HTML)
assert fixed_detail == "5,000,000주 · 주당 $10.00 · 총 $50,000,000.00", \
    f"확정공모 조건을 잘못 뽑음: {fixed_detail!r}"
assert sec_filings._extract_offering_detail("<html><body>관련 없는 문서</body></html>") is None, \
    "표지 형식이 안 맞는데도 조건을 지어냄"
print(f"3) 조건 추출 OK — ATM={atm_detail!r}, 확정공모={fixed_detail!r}, 매칭 실패 시 None")

# --- 4) find_capital_raise_filings() 반환 형식 + 조건이 헤드라인에 붙는지 ----------------
sec_filings.get_cik = lambda ticker: FAKE_CIK
results = sec_filings.find_capital_raise_filings("FAKE")
assert len(results) == 3, f"개수가 안 맞음: {len(results)}"
by_accession = {r["url"]: r for r in results}

fixed_result = by_accession[_index_url(FIXED_ACCESSION)]
assert fixed_result["headline"] == (
    "424B5 공시 — 투자설명서 보충(Shelf 공모 실행) "
    "(5,000,000주 · 주당 $10.00 · 총 $50,000,000.00)"
), f"확정공모 헤드라인이 안 맞음: {fixed_result['headline']!r}"

atm_result = by_accession[_index_url(B5_ACCESSION)]
assert "최대 $6,000,000,000" in atm_result["headline"], \
    f"ATM 헤드라인에 한도가 안 붙음: {atm_result['headline']!r}"

recent_result = by_accession[_index_url(RECENT_ACCESSION)]
assert recent_result["headline"] == "S-3 공시 — 간이 증권 등록(Shelf)", \
    f"문서를 못 찾은 건인데 조건을 지어냄: {recent_result['headline']!r}"

assert fixed_result["categories"] == [{"category": "유상증자·자본조달", "matched": ["424B5"]}]
assert fixed_result["source"] == "SEC EDGAR"
assert isinstance(fixed_result["datetime"], int), \
    f"datetime이 epoch(int)가 아님: {fixed_result['datetime']!r}"
print(f"4) 헤드라인 부착/폴백 OK\n   - {fixed_result['headline']}\n   - {atm_result['headline']}\n   - {recent_result['headline']}")

# --- 5) CIK를 못 찾은 티커 → 조용히 빈 리스트 ---------------------------------------
sec_filings.get_cik = lambda ticker: None
assert sec_filings.find_capital_raise_filings("NOSUCHTICKER") == []
print("5) CIK 미확인 티커 → [] OK")


# --- 6) 네트워크 실패 → 예외 없이 빈 리스트 -----------------------------------------
def fake_get_broken(url, **kwargs):
    raise ConnectionError("network down")


sec_filings.requests.get = fake_get_broken
sec_filings.get_cik = lambda ticker: FAKE_CIK
assert sec_filings.find_capital_raise_filings("FAKE") == [], "네트워크 실패 시 예외가 새어나감"
print("6) 네트워크 실패 → [] OK (예외 안 새어나감)")

print("\n전부 통과")
