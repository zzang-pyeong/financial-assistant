"""관계도 보강 — SEC EDGAR 공시 기반 관계 탐색 (2026-07-25 신규).

뉴스 기반 관계도(lib/qualitative.py::match_counterparties)는 최근 60일 M&A/파트너십
키워드 뉴스에만 의존해서 커버리지가 낮다는 실측 피드백을 받음(NVDA 검색 시 티커당
2~3개 엣지뿐). SEC EDGAR Full-Text Search는 완전 무료·키 불필요하고, 10-K/10-Q/8-K가
실제 공급망·고객·파트너 관계를 몇 년치나 담고 있어 훨씬 권위 있는 보강 소스가 됨
(실측: NVDA 10-K가 "Taiwan Semiconductor"를 26회, "Micron"을 최근 3개 연도 10-K에서
언급 — 둘 다 뉴스 기반 관계도에는 전혀 안 잡히던 관계).

⚠️ 일반적인 관계 유형 문구("supply agreement", "strategic partnership")를 그대로
검색하면 거의 안 걸림(실측: NVDA 최근 2년 "supply agreement" 검색 0건) — 공시는 격식체
언어를 써서 뉴스와 다른 어휘를 씀. 그래서 문구 매칭이 아니라 "상대 회사 이름 자체가
본문에 등장하는지"로 검색한다. 대신 정밀 관계 유형·방향성은 알 수 없음 — "공시 내 언급"
(근거 등급 D, 기본 화면에서는 숨김)까지만 표시하고, 실제 문맥은 사용자가 링크를 눌러
원문에서 직접 확인해야 한다(과확신 방지).

2026-07-27 추가: Exhibit 21(자회사 목록)과 Schedule 13D/13G(대량 지분 보유)는 반대로
근거 등급 A — 구조화된 SEC 공식 문서에서 관계를 직접 명시하기 때문(추측이 아니라 문서에
적힌 그대로). 이 둘은 일반 언급 검색과 달리 소량(회사당 최대 30개 자회사, 최근 2년
13D/13G)만 조회하고 실패 시 조용히 빈 리스트를 반환한다(find_subsidiaries,
find_beneficial_owners 참고).
"""

import codecs
import html
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta

import requests
import streamlit as st

_USER_AGENT = "EnterTicker research contact@example.com"
_FORMS = "10-K,10-Q,8-K"
_MAX_WORKERS = 5

# 법인 접미사만 제거 — 뉴스 매칭(_company_tokens)과 달리 "semiconductor"/"technology" 같은
# 업종 일반명사는 남겨둔다. 공시에서는 "Taiwan Semiconductor"처럼 그 단어 자체가 회사명의
# 핵심인 경우가 많아서(실측: "semiconductor" 빼면 "Taiwan"만 남아 정확도가 떨어짐).
_LEGAL_SUFFIXES = re.compile(
    r"\s*,?\s*(inc\.?|incorporated|corp\.?|corporation|co\.?|ltd\.?|limited|plc|"
    r"holdings?|group|company|s\.?a\.?|n\.?v\.?|ag|llc|l\.?p\.?|trust)\s*$",
    re.IGNORECASE,
)


def _filing_search_phrase(name):
    """공시 검색용 구문 — 법인 접미사만 반복 제거한 최대 축약형(예: "Arm Holdings plc"
    → "Arm"). 여러 후보 중 가장 짧고 회사명 핵심만 남는 형태라 재현율은 높지만, "Arm"/
    "Apple"처럼 흔한 영단어로 축약되면 오탐 위험도 커짐 — 그래서 이 함수를 곧바로 검색에
    쓰지 말고 아래 _filing_search_candidates()의 최후 단계로만 사용할 것."""
    cleaned = (name or "").strip()
    prev = None
    while cleaned and cleaned != prev:
        prev = cleaned
        cleaned = _LEGAL_SUFFIXES.sub("", cleaned).strip()
    return cleaned


def _single_suffix_strip(name):
    """접미사를 딱 한 겹만 제거(반복 안 함) — 정식 법인명과 최대 축약형 사이의 중간
    안전 단계("안전한 별칭"). 예: "Arm Holdings plc" → "Arm Holdings"(아직 "Holdings"가
    남아있어 "Arm" 단독보다 훨씬 덜 흔함)."""
    cleaned = (name or "").strip()
    return _LEGAL_SUFFIXES.sub("", cleaned).strip()


# 완전 축약 시 흔한 영단어로 남는 게 실측으로 확인된 후보 — 이 단어들로만 히트가 나면
# 오탐 경고를 붙인다. "Arm"은 "at arm's length"(특수관계자거래 상투 문구), "Apple"은
# "apple-to-apple(s) comparison"(비교 관용구)에서 유래한 것으로 보임(AMKR이라는 Arm/Apple과
# 무관한 회사의 공시에서 실제로 각각 9건/5건 히트되는 것으로 검증함). 다른 축약형(Oracle,
# Tesla, Diodes, Intel 등)은 같은 방식으로 검증했을 때 오탐이 거의 없어 제외.
_AMBIGUOUS_BARE_WORDS = {"arm", "apple"}


def _filing_search_candidates(name):
    """검색을 시도할 구문을 "정식 법인명 → 접미사 1단계 제거(안전한 별칭) → 완전 축약"
    순서로 반환(중복 제거). find_filing_relationships()가 이 순서대로 시도하다가 첫
    히트에서 멈춘다 — 대부분의 회사명은 접미사가 한 겹뿐이라 세 단계가 실질적으로
    1~2개로 줄어들어(중복 제거) API 호출이 크게 늘지 않는다."""
    raw = (name or "").strip()
    if not raw:
        return []
    single = _single_suffix_strip(raw)
    full = _filing_search_phrase(raw)
    candidates = []
    for phrase in (raw, single, full):
        if phrase and phrase not in candidates:
            candidates.append(phrase)
    return candidates


@st.cache_data(ttl=86400, show_spinner=False)
def _get_ticker_cik_map():
    """티커 → 10자리 zero-padded CIK. SEC가 통째로 제공하는 정적 파일, 무료·키 불필요."""
    try:
        r = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers={"User-Agent": _USER_AGENT}, timeout=10,
        )
        data = r.json()
        return {
            row["ticker"].upper(): str(row["cik_str"]).zfill(10)
            for row in data.values()
        }
    except Exception:
        return {}


def get_cik(ticker):
    return _get_ticker_cik_map().get((ticker or "").upper())


@st.cache_data(ttl=86400, show_spinner=False)
def _get_name_to_ticker_map():
    """등록회사명(정규화) → 티커. 자회사(Exhibit 21)나 13D/13G 보고자 이름을 상장 티커로
    되짚어보려 할 때 쓴다 — 대부분 실패하는 게 정상이다(자회사는 대개 비상장, 13D/13G
    보고자도 개인·비상장 펀드가 흔함). company_tickers.json은 이미 _get_ticker_cik_map()도
    받는 같은 파일이라 요청이 중복되지만, 둘 다 하루 캐시라 실질 비용은 작다."""
    try:
        r = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers={"User-Agent": _USER_AGENT}, timeout=10,
        )
        data = r.json()
        return {
            re.sub(r"[^a-z0-9]", "", row["title"].lower()): row["ticker"].upper()
            for row in data.values() if row.get("title")
        }
    except Exception:
        return {}


def _match_known_ticker(name):
    """회사명으로 상장 티커를 찾는다. 못 찾으면 빈 문자열 — 티커를 추측해 채우지 않는다."""
    if not name:
        return ""
    key = re.sub(r"[^a-z0-9]", "", name.lower())
    return _get_name_to_ticker_map().get(key, "")


@st.cache_data(ttl=86400, show_spinner=False)
def _search_filings_for_company(target_cik, phrase, lookback_days=730):
    """target_cik의 공시(10-K/10-Q/8-K, 최근 lookback_days)에서 phrase가 본문에 등장하는
    공시 목록을 반환. 실패/빈 결과는 조용히 빈 리스트(lib/data.py의 다른 함수들과 동일 패턴)."""
    if not target_cik or not phrase:
        return []
    today = date.today()
    try:
        r = requests.get(
            "https://efts.sec.gov/LATEST/search-index",
            params={
                "q": f'"{phrase}"',
                "ciks": target_cik,
                "forms": _FORMS,
                "startdt": (today - timedelta(days=lookback_days)).isoformat(),
                "enddt": today.isoformat(),
            },
            headers={"User-Agent": _USER_AGENT},
            timeout=10,
        )
        data = r.json()
        hits = []
        for h in data.get("hits", {}).get("hits", []):
            src = h.get("_source", {})
            accession, _, filename = h.get("_id", "").partition(":")
            if not accession or not filename:
                continue
            hits.append({
                "form": src.get("form"),
                "file_date": src.get("file_date"),
                "accession": accession,
                "filename": filename,
            })
        return hits
    except Exception:
        return []


def _filing_url(target_cik, hit):
    cik_no_padding = str(int(target_cik))
    accession_no_dashes = hit["accession"].replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik_no_padding}/{accession_no_dashes}/{hit['filename']}"


def _file_date_to_epoch(file_date_str):
    try:
        return int(datetime.strptime(file_date_str, "%Y-%m-%d").timestamp())
    except Exception:
        return 0


def _phrases_for(name):
    """이름 하나에 대한 검색 후보 구문 목록. 완전 축약형이 흔한 단어일 때만 단계적
    후보(정식명→별칭→축약)를 만들고, 아니면 축약형 1개만 반환 — 대부분(peer+정적
    목록 중 실측 2개만 예외)은 1회 검색으로 끝나 API 호출이 거의 안 늘어남."""
    full = _filing_search_phrase(name)
    if not full:
        return []
    if full.lower() in _AMBIGUOUS_BARE_WORDS:
        return _filing_search_candidates(name)
    return [full]


def _search_cascade(cik, phrases):
    """정식 법인명 → 안전한 별칭 → 완전 축약 순서로 시도, 첫 히트에서 멈춘다.
    완전 축약 단계까지 가서야 히트가 나고 그 구문이 흔한 단어면 ambiguous=True —
    정식명/별칭 단계에서 이미 히트가 있었으면 이 위험한 단계 자체를 시도하지 않는다."""
    for i, phrase in enumerate(phrases):
        hits = _search_filings_for_company(cik, phrase)
        if hits:
            is_last_resort = i == len(phrases) - 1 and phrase.lower() in _AMBIGUOUS_BARE_WORDS
            return hits, is_last_resort
    return [], False


def find_filing_relationships(target_ticker, target_name, known_companies, on_progress=None):
    """양방향 검색 — (A) target_ticker의 공시에서 known_companies(peer+정적목록,
    [{"ticker":, "name":}, ...]) 각각이 언급되는지(정방향), (B) known_companies 각자의
    공시에서 target_name이 언급되는지(역방향)를 함께 병렬 검색.

    역방향을 추가한 이유: 정방향만으로는 IREN처럼 작은 상대회사가 "우리가 NVIDIA와
    계약했다"를 자기 공시에는 크게 실었어도 대상 종목(NVIDIA) 쪽 공시엔 안 나타나면
    영영 못 잡음(실측으로 확인된 한계). 상대회사 수만큼 SEC 호출이 추가로 늘어나
    총 호출량이 대략 2배가 되지만, known_companies 규모(peer+정적목록 ~100개)에서는
    병렬 처리로 감당 가능한 수준.

    on_progress(done, total)를 완료될 때마다 호출(진행률 표시용). 히트마다 엣지 하나씩
    반환 — 기존 뉴스 기반 엣지와 같은 스키마(relationship_type/status/evidence_level/
    headline/url/datetime)라 render_relationship_graph_figure의 그룹핑 로직을 그대로
    재사용할 수 있음. 대상/상대 어느 쪽이든 CIK를 못 찾으면(비상장·외국 민간발행사 등)
    그 방향의 검색만 조용히 빈 결과로 건너뜀."""
    target_cik = get_cik(target_ticker)
    target_phrases = _phrases_for(target_name)

    forward_candidates = []
    reverse_candidates = []
    for kc in known_companies:
        cp_ticker = (kc.get("ticker") or "").upper()
        if not cp_ticker or cp_ticker == target_ticker.upper():
            continue
        cp_name = kc.get("name")
        if target_cik:
            phrases = _phrases_for(cp_name)
            if phrases:
                forward_candidates.append((cp_ticker, cp_name, phrases))
        if target_phrases:
            cp_cik = get_cik(cp_ticker)
            if cp_cik:
                reverse_candidates.append((cp_ticker, cp_name, cp_cik))

    edges = []
    total = len(forward_candidates) + len(reverse_candidates)
    done = 0
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        futures = {}
        for cp_ticker, cp_name, phrases in forward_candidates:
            future = executor.submit(_search_cascade, target_cik, phrases)
            futures[future] = ("forward", cp_ticker, cp_name, target_cik)
        for cp_ticker, cp_name, cp_cik in reverse_candidates:
            future = executor.submit(_search_cascade, cp_cik, target_phrases)
            futures[future] = ("reverse", cp_ticker, cp_name, cp_cik)

        for future in as_completed(futures):
            direction, cp_ticker, cp_name, doc_cik = futures[future]
            hits, ambiguous = future.result()

            if direction == "forward":
                evidence_level = "공시 자료 (SEC EDGAR, 공식 문서)"
                snippet_name = cp_name
            else:
                evidence_level = "공시 자료 (상대 회사 공시에서 확인, SEC EDGAR)"
                snippet_name = target_name
            if ambiguous:
                evidence_level = "⚠️ 흔한 단어 검색이라 오탐 가능 · " + evidence_level

            for hit in hits:
                if direction == "forward":
                    headline = f"{hit['form']} ({hit['file_date']}) 공시에 '{cp_name}' 언급"
                else:
                    headline = f"{cp_name}의 {hit['form']} ({hit['file_date']}) 공시에 '{target_name}' 언급"
                edges.append({
                    "counterparty_ticker": cp_ticker,
                    "counterparty_name": cp_name,
                    "relationship_type": "공시 내 언급",
                    "direction": "unknown",
                    "status": "미확인",
                    "evidence_grade": "D",
                    "evidence_level": evidence_level,
                    "source_kind": "SEC 공시",
                    "headline": headline,
                    "url": _filing_url(doc_cik, hit),
                    "datetime": _file_date_to_epoch(hit["file_date"]),
                    "snippet_query_name": snippet_name,
                    "ownership_pct": None,
                    "transaction_value": None,
                    "extraction_method": "mention",
                })
            done += 1
            if on_progress:
                on_progress(done, total)
    return edges


# ---------------------------------------------------------------------------
# Exhibit 21 자회사 목록 — 구조화된 SEC 공식 문서라 근거 등급 A. 최근 10-K의 EX-21
# 첨부문서를 찾아 표를 파싱한다. 형식이 필사마다 다른데(표 vs 텍스트 나열) 표 형식만
# 지원한다 — 못 찾거나 파싱에 실패하면 조용히 빈 리스트를 반환해서, 이 기능이 실패해도
# 관계도 나머지가 깨지지 않게 한다(지시서 원칙: 부분 실패를 조용히 처리).
# ---------------------------------------------------------------------------
_MAX_SUBSIDIARIES = 30
_TR_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL | re.IGNORECASE)
_CELL_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.DOTALL | re.IGNORECASE)
_SUBSIDIARY_HEADER_RE = re.compile(
    r"^name$|name of (the )?subsidiar|jurisdiction|state of incorporation|"
    r"where incorporated|incorporated in|organized under",
    re.IGNORECASE,
)


@st.cache_data(ttl=86400, show_spinner=False)
def _get_recent_10k_accession(cik):
    """CIK의 가장 최근 10-K (accession number, 제출일) — SEC submissions API는 회사당
    최근 제출 이력을 통째로 주므로(무료·키 불필요) 이걸로 최신 연차보고서를 찾는다."""
    if not cik:
        return None, None
    try:
        r = requests.get(
            f"https://data.sec.gov/submissions/CIK{cik}.json",
            headers={"User-Agent": _USER_AGENT}, timeout=10,
        )
        recent = r.json().get("filings", {}).get("recent", {})
        for form, accession, fdate in zip(
            recent.get("form", []), recent.get("accessionNumber", []),
            recent.get("filingDate", []),
        ):
            if form == "10-K":
                return accession, fdate
    except Exception:
        pass
    return None, None


_INDEX_HREF_RE = re.compile(r'href="([^"]+)"', re.IGNORECASE)


def _list_filing_documents(cik, accession):
    """공시 하나(accession)의 "Document Format Files" 표에서 [{"name":, "type":}, ...]를
    뽑는다. 디렉터리 인덱스(index.json)의 "type" 필드는 실제 문서 타입이 아니라 아이콘
    힌트일 뿐이라서(실측: NVDA 10-K에서 htm 파일 전부가 "text.gif") 못 쓴다 — 사람이 보는
    -index.htm 표에만 진짜 Exhibit 타입(예: "EX-21.1")이 있어서 이걸 파싱한다."""
    if not cik or not accession:
        return []
    try:
        cik_no_padding = str(int(cik))
        accession_no_dashes = accession.replace("-", "")
        url = (
            f"https://www.sec.gov/Archives/edgar/data/{cik_no_padding}/"
            f"{accession_no_dashes}/{accession}-index.htm"
        )
        r = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=10)
        text = r.text
    except Exception:
        return []

    docs = []
    for tr in _TR_RE.finditer(text):
        cells_html = _CELL_RE.findall(tr.group(1))
        if len(cells_html) < 4:
            continue
        href_m = _INDEX_HREF_RE.search(cells_html[2])
        if not href_m:
            continue
        name = href_m.group(1).rsplit("/", 1)[-1]
        doc_type = _clean_fragment(cells_html[3]).strip()
        if name:
            docs.append({"name": name, "type": doc_type})
    return docs


def _parse_subsidiary_rows(html_text):
    """Exhibit 21 HTML에서 표 행을 파싱해 [(이름, 관할), ...]로 반환. 표가 아니면(텍스트
    나열형 등) 빈 리스트 — 이번 범위에서는 표 형식만 지원한다."""
    rows = []
    for tr in _TR_RE.finditer(html_text):
        cells = [_clean_fragment(c).strip() for c in _CELL_RE.findall(tr.group(1))]
        cells = [c for c in cells if c]
        if not cells:
            continue
        # 제목행("Subsidiaries of Registrant...")과 실제 헤더행("Name of Subsidiary" |
        # "State... of Incorporation")이 셀만 다를 뿐 같은 <tr>에 같이 들어있는 경우가
        # 있어(실측: NVDA), 첫 셀만 보면 못 거른다 — 행의 모든 셀을 검사한다.
        if any(_SUBSIDIARY_HEADER_RE.search(c) for c in cells):
            continue
        name = cells[0]
        jurisdiction = cells[1] if len(cells) > 1 else ""
        if len(name) >= 2 and not name.replace(".", "").isdigit():
            rows.append((name, jurisdiction))
    return rows


def find_subsidiaries(ticker):
    """최근 10-K의 Exhibit 21(자회사 목록)에서 자회사명·관할을 추출해 표준 스키마 엣지로
    반환한다. (엣지 목록, 잘렸는지 여부) 튜플. 상장 티커를 찾을 수 있으면 매핑하고, 못
    찾으면 counterparty_ticker=""(회사명만 표시, 추측해 채우지 않음). 30개를 넘으면
    앞에서부터 30개만 반환하고 잘렸다고 표시한다. 어느 단계든 실패하면 ([], False)."""
    cik = get_cik(ticker)
    accession, filing_date = _get_recent_10k_accession(cik)
    if not accession:
        return [], False

    docs = _list_filing_documents(cik, accession)
    exhibit = next((d for d in docs if d["type"].upper().startswith("EX-21")), None)
    if not exhibit:
        exhibit = next(
            (d for d in docs if re.search(r"ex[\-_]?21", d["name"], re.IGNORECASE)), None,
        )
    if not exhibit or not exhibit.get("name"):
        return [], False

    cik_no_padding = str(int(cik))
    accession_no_dashes = accession.replace("-", "")
    url = (
        f"https://www.sec.gov/Archives/edgar/data/{cik_no_padding}/"
        f"{accession_no_dashes}/{exhibit['name']}"
    )
    try:
        r = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=15)
        rows = _parse_subsidiary_rows(r.text)
    except Exception:
        return [], False

    truncated = len(rows) > _MAX_SUBSIDIARIES
    rows = rows[:_MAX_SUBSIDIARIES]
    filing_dt = _file_date_to_epoch(filing_date) if filing_date else None

    edges = []
    for name, jurisdiction in rows:
        detail = f" ({jurisdiction} 법인)" if jurisdiction else ""
        edges.append({
            "counterparty_ticker": _match_known_ticker(name),
            "counterparty_name": name,
            "relationship_type": "자회사",
            "direction": "outbound",
            "status": "진행",
            "evidence_grade": "A",
            "evidence_level": "공식 SEC Exhibit 21 (자회사 목록)",
            "source_kind": "SEC 공시",
            "headline": f"Exhibit 21 자회사 목록에 등재{detail}",
            "context": None,
            "url": url,
            "datetime": filing_dt,
            "ownership_pct": None,
            "transaction_value": None,
            "extraction_method": "rule",
        })
    return edges, truncated


# ---------------------------------------------------------------------------
# Schedule 13D/13G 대량 지분 보유 — 구조화된 SEC 공식 문서라 근거 등급 A. 보고자
# (reporting person) 이름과 지분율을 문서 원문에서 정규식으로 추출한다. 표지 페이지
# 형식이 필사마다 달라 이름을 못 찾으면 그 건은 조용히 건너뛴다(가짜 근거를 만들지
# 않는다는 지시서 원칙 7). 13F(일반 운용 보유)·Form 3/4/5(내부자)는 지시서에 따라
# 전략적 투자 관계로 오해될 수 있어 이번 범위에서 다루지 않는다.
# ---------------------------------------------------------------------------
_MAX_OWNERSHIP_FILINGS = 15
_ATOM_ENTRY_RE = re.compile(r"<entry>(.*?)</entry>", re.DOTALL | re.IGNORECASE)
_ATOM_FIELD_RES = {
    "type": re.compile(r"<filing-type>(.*?)</filing-type>", re.IGNORECASE),
    "date": re.compile(r"<filing-date>(.*?)</filing-date>", re.IGNORECASE),
    "accession": re.compile(r"<accession-number>(.*?)</accession-number>", re.IGNORECASE),
}
# SC 13D/13G 표지 페이지의 "NAMES OF REPORTING PERSONS" 항목 뒤에 오는 이름을 잡는다.
# 표 형식·줄바꿈이 필사마다 달라 완벽하지 않다 — 못 찾으면 그 건은 건너뛴다.
# 이름 뒤 정지 지점을 룩어헤드로 둔다(소비하지 않음) — 실측(RDW 13G)에서 다음 필드가
# "2 CHECK THE APPROPRIATE BOX"처럼 예상 못한 문구로 시작해서 원래 "CHECK IF"만 찾던
# 패턴이 실패했다. 표지 페이지는 매 필드가 "<번호> <대문자 라벨>"로 시작하는 게
# 공통이라(2 CHECK.../3 SEC.../4 CITIZENSHIP...), 그 패턴을 우선 정지 조건으로 쓴다.
_REPORTING_PERSON_RE = re.compile(
    r"NAMES?\s+OF\s+REPORTING\s+PERSONS?[.:\s]*([A-Z][A-Za-z0-9&.,'\-\s]{2,80}?)"
    r"(?=\s+\(?\d{1,2}\)?\s+[A-Z]|\s+S\.?S\.?\s+OR|\s+I\.?R\.?S\.?|\s+CHECK|$)",
    re.IGNORECASE,
)
# 실측(NVDA 13G/A): 요즘 상당수 13D/13G가 고전적인 표지 문구 대신 XBRL에서 뽑아낸
# "Item 1: Reporting Person - FMR LLC ... Item 11: 4.069%" 형태의 압축된 텍스트를 쓴다
# ("PERCENT OF CLASS" 같은 설명 문구 자체가 없음) — 이 형식을 위한 대체 패턴.
_REPORTING_PERSON_ALT_RE = re.compile(
    r"Reporting\s+Person\s*-\s*([A-Z][A-Za-z0-9&.,'\-\s]{2,80}?)\s*(?:Item\s*2|$)",
    re.IGNORECASE,
)
_PERCENT_OF_CLASS_RE = re.compile(
    # "ROW (9)"처럼 라벨과 실제 숫자 사이에 행 번호(숫자)가 섞여 있어 숫자를 무조건
    # 배제하면 못 찾는다 — 실측(RDW 13G)으로 확인. 대신 아무 문자나 허용하고(비탐욕)
    # "숫자(.숫자)? %" 패턴이 나오는 첫 지점을 잡는다.
    r"PERCENT\s+OF\s+CLASS.{0,100}?(\d{1,2}(?:\.\d+)?)\s*%", re.IGNORECASE | re.DOTALL,
)
_PERCENT_ITEM11_RE = re.compile(r"Item\s*11:\s*(\d{1,2}(?:\.\d+)?)\s*%", re.IGNORECASE)
_OWNERSHIP_ENDED_RE = re.compile(
    r"no longer beneficially owns|ceased to be the beneficial owner|has sold",
    re.IGNORECASE,
)


def _extract_pattern(pattern, text, default=None):
    m = pattern.search(text)
    return html.unescape(m.group(1)).strip() if m else default


def _list_13d_13g_filings(cik, lookback_days=730):
    """대상 CIK가 issuer인 최근 lookback_days 안의 Schedule 13D/13G(및 /A 정정) 목록을
    EDGAR 회사별 공시 이력(Atom feed)에서 가져온다. 전문검색 API(_search_filings_for_company
    가 쓰는 것)는 검색어가 필수라 이 용도에 안 맞아서, 검색어 없이 "이 회사 관련 이 유형의
    공시 전부"를 주는 이 엔드포인트를 대신 쓴다."""
    if not cik:
        return []
    cutoff = date.today() - timedelta(days=lookback_days)
    seen = set()
    filings = []
    for form_type in ("SC 13D", "SC 13G"):
        try:
            r = requests.get(
                "https://www.sec.gov/cgi-bin/browse-edgar",
                params={
                    "action": "getcompany", "CIK": cik, "type": form_type,
                    "dateb": "", "owner": "include", "count": 100, "output": "atom",
                },
                headers={"User-Agent": _USER_AGENT}, timeout=10,
            )
            text = r.text
        except Exception:
            continue
        for m in _ATOM_ENTRY_RE.finditer(text):
            block = m.group(1)
            accession = _extract_pattern(_ATOM_FIELD_RES["accession"], block)
            fdate = _extract_pattern(_ATOM_FIELD_RES["date"], block)
            if not accession or accession in seen:
                continue
            if fdate:
                try:
                    if datetime.strptime(fdate, "%Y-%m-%d").date() < cutoff:
                        continue
                except Exception:
                    pass
            seen.add(accession)
            filings.append({
                "accession": accession,
                "form": _extract_pattern(_ATOM_FIELD_RES["type"], block) or form_type,
                "date": fdate,
            })
    filings.sort(key=lambda f: f.get("date") or "", reverse=True)
    return filings[:_MAX_OWNERSHIP_FILINGS]


def _primary_document_url(cik, accession):
    docs = _list_filing_documents(cik, accession)
    primary = next(
        (d for d in docs if d["type"].upper().startswith(("SC 13D", "SC 13G"))), None,
    )
    if not primary:
        primary = next(
            (d for d in docs if d["name"].lower().endswith((".htm", ".html", ".txt"))), None,
        )
    if not primary:
        return None
    cik_no_padding = str(int(cik))
    accession_no_dashes = accession.replace("-", "")
    return (
        f"https://www.sec.gov/Archives/edgar/data/{cik_no_padding}/"
        f"{accession_no_dashes}/{primary['name']}"
    )


def _process_13d_13g_filing(cik, filing):
    url = _primary_document_url(cik, filing["accession"])
    if not url:
        return None
    try:
        r = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=15)
        cleaned = _clean_fragment(r.text)
    except Exception:
        return None

    name = (
        _extract_pattern(_REPORTING_PERSON_RE, cleaned)
        or _extract_pattern(_REPORTING_PERSON_ALT_RE, cleaned)
    )
    if not name:
        return None
    pct_str = (
        _extract_pattern(_PERCENT_OF_CLASS_RE, cleaned)
        or _extract_pattern(_PERCENT_ITEM11_RE, cleaned)
    )
    pct = None
    if pct_str:
        try:
            pct = float(pct_str)
        except ValueError:
            pct = None
    status = "완료" if _OWNERSHIP_ENDED_RE.search(cleaned) else "진행"

    return {
        "counterparty_ticker": _match_known_ticker(name),
        "counterparty_name": name,
        "relationship_type": "지분 투자·보유",
        "direction": "inbound",
        "status": status,
        "evidence_grade": "A",
        "evidence_level": "SEC Schedule 13D/13G 대량 지분 보유 공시",
        "source_kind": "SEC 공시",
        "headline": (
            f"{filing['form']} ({filing['date']}) — {name}"
            + (f", 지분 {pct:.1f}%" if pct is not None else "")
        ),
        "context": None,
        "url": url,
        "datetime": _file_date_to_epoch(filing["date"]) if filing.get("date") else None,
        "ownership_pct": pct,
        "transaction_value": None,
        "extraction_method": "rule",
    }


def find_beneficial_owners(ticker):
    """최근 2년 Schedule 13D/13G에서 보고자(reporting person)와 지분율을 추출해 표준
    스키마 엣지로 반환한다. 보고자 이름을 못 찾으면(표지 페이지 형식 인식 실패) 그 건은
    건너뛴다 — 이름 없는 엣지를 만들지 않는다. 지분율은 확실히 뽑힐 때만 채운다."""
    cik = get_cik(ticker)
    if not cik:
        return []
    filings = _list_13d_13g_filings(cik)
    if not filings:
        return []
    with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(filings))) as executor:
        results = list(executor.map(lambda f: _process_13d_13g_filing(cik, f), filings))
    ticker_upper = ticker.upper()
    # 실측(PLTR): 발행회사 자신이 표지 페이지의 "NAMES OF REPORTING PERSONS"에 잘못 걸리는
    # 문서가 있었다(자사주 관련 특수 케이스로 보임) — 자기 자신을 보유자로 표시하는 건
    # 의미가 없으므로 걸러낸다.
    return [
        r for r in results
        if r and (not r["counterparty_ticker"] or r["counterparty_ticker"] != ticker_upper)
    ]


# ---------------------------------------------------------------------------
# 문맥 추출 — 검색 API는 스니펫을 안 줘서(실측 확인), 문서 원문을 받아 회사명 주변을
# 직접 잘라낸다. re + html + codecs(전부 표준 라이브러리)만 사용 — 새 의존성 없음.
#
# 2026-07-27 비용 최적화. 이전 구현에는 문제가 셋 있었다:
#   1) 문서를 통째로 받았다 — 10-K는 5~20MB가 흔한데, 우리가 필요한 건 회사명 주변
#      360자뿐이다. 상위 20개 회사면 수백 MB를 받아놓고 거의 다 버리는 셈이었다.
#   2) 그 수 MB짜리 정제 텍스트 전체를 @st.cache_data에 넣었다 — Streamlit 캐시가
#      티커·회사 조합마다 부풀어 올랐다.
#   3) 그 캐시 함수를 ThreadPoolExecutor 워커에서 호출했다 — st.cache_data는 스크립트
#      실행 컨텍스트를 기대해서 워커 스레드에서 부르면 ScriptRunContext 경고가 난다.
# 그래서 (1) 스트리밍으로 받다가 회사명을 찾는 즉시 연결을 끊고 (2) 캐시는 결과 스니펫
# (수백 바이트)만 (3) Streamlit에 의존하지 않는 평범한 dict으로 들고 있게 바꿨다.
# ---------------------------------------------------------------------------
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_ANY_TAG_RE = re.compile(r"<[^>]+>")

# 그래프는 이제 상대기업을 전부 다 그리지만(lib/charts.py), 회사마다 공시 원문을 받아
# 스니펫을 뽑는 건 시간이 걸려서(스트리밍이라 빨라도 요청 자체는 남음) 전체에 다 걸면
# 페이지가 느려진다. 근거가 가장 많은 상위 N개에만 실제 문맥을 채우고, 나머지는 요약
# 표에서 "원문 확인 필요" 안내로 자연스럽게 폴백된다(pages/8_관계도.py::_best_description).
_MAX_SNIPPET_COMPANIES = 10

# 스트리밍 중 이 크기를 넘게 읽었는데도 회사명을 한 번도 못 찾으면 포기한다(비정상적으로
# 큰 첨부가 붙은 공시로부터 스스로를 보호). 실측상 회사명은 보통 앞쪽 수백 KB 안에 나온다.
_MAX_FILING_BYTES = 6 * 1024 * 1024
_STREAM_CHUNK = 64 * 1024

# 여러 매칭 후보를 모으기 위한 상한 — 첫 매칭에서 바로 멈추던 것보다는 더 읽어야 한다.
# 그래도 6MB 안전장치보다는 훨씬 작게 잡아서(실측상 사업설명은 문서 앞쪽에 나옴) 대부분의
# 문서는 이 안에서 여러 매칭을 확보하고 끝난다. 이 안에서 하나도 못 찾은 극히 일부 문서만
# _MAX_FILING_BYTES까지 계속 읽어 최소 1건은 건지려 한다(재현율 유지).
_CANDIDATE_SCAN_BYTES = 1_500_000
_MAX_CANDIDATES = 6

# 스니펫 캐시 — 제출된 공시는 내용이 안 바뀌므로 (url, 회사명) → 스니펫은 영구히 유효하다.
# st.cache_data 대신 평범한 dict을 쓰는 이유는 위 주석 (3)번(워커 스레드 호출) 때문.
_SNIPPET_CACHE = {}
_SNIPPET_CACHE_MAX = 2000


def _clean_fragment(fragment):
    """HTML 조각에서 태그를 벗기고 엔티티를 풀어 공백을 정규화한다."""
    text = _SCRIPT_STYLE_RE.sub(" ", fragment)
    text = _ANY_TAG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", html.unescape(text))


def _safe_split_point(raw):
    """조각 끝에 태그가 잘려 걸쳐 있으면(예: "...<td cla") 그 앞까지만 이번에 처리하고
    나머지는 다음 조각과 이어 붙이도록, 안전하게 자를 수 있는 위치를 돌려준다.
    이걸 안 하면 청크 경계에서 태그가 반토막 나 스니펫에 '<td class=' 같은 게 섞인다."""
    last_open = raw.rfind("<")
    if last_open == -1:
        return len(raw)
    # 마지막 '<' 뒤에 '>'가 있으면 그 태그는 이미 닫힌 것 — 통째로 처리해도 안전
    return len(raw) if raw.find(">", last_open) != -1 else last_open


# "관계도 표에 뭘 하는지 안 보인다"는 피드백 — 예전엔 매칭 지점 앞뒤로 고정 폭(±180자)만
# 잘랐어서 "...etermination, the value of..." 처럼 단어 중간에서 끊긴 스니펫이 나왔다.
# 문장 경계에서 자르면 훨씬 읽을 만해진다. 마침표 뒤에 대문자/인용부호가 오는 지점만
# 문장 끝으로 인정해 "Inc."·"U.S." 같은 약어의 마침표를 오판할 여지를 조금 줄인다 —
# 완벽하진 않지만(약어 뒤에 대문자 문장이 바로 오면 여전히 오판 가능), 고정폭 절단보다는
# 항상 낫다.
_SENTENCE_BOUNDARY_RE = re.compile(r'(?<=[.!?])\s+(?=[A-Z"‘“])')
_MAX_SENTENCE_CHARS = 320


def _trim_to_sentence(text, match_start, match_len):
    """text 안에서 [match_start, match_start+match_len) 구간(회사명)을 포함하는 문장만
    골라 반환한다. (문장, 시작이_잘렸는지, 끝이_잘렸는지) 튜플 — 잘림 여부는 호출부가
    "…" 표시 여부를 정하는 데 쓴다. 문장 경계를 못 찾으면(text 끝까지 가도 없음)
    text 전체를 잘린 것으로 간주해 반환."""
    bounds = [0] + [m.end() for m in _SENTENCE_BOUNDARY_RE.finditer(text)] + [len(text)]
    match_end = match_start + match_len
    for i in range(len(bounds) - 1):
        s, e = bounds[i], bounds[i + 1]
        if s <= match_start < e:
            # 회사명이 문장 경계 판정 지점을 걸쳐 있으면(약어 오판 등) 다음 문장까지 합친다
            while e < match_end and i + 1 < len(bounds) - 1:
                i += 1
                e = bounds[i + 1]
            return text[s:e].strip(), s == 0, e == len(text)
    return text.strip(), True, True


def _find_all_occurrences(tail, phrases, max_candidates):
    """tail 안에서 phrases 중 하나라도 매칭되는 지점을 등장 순서대로 최대 max_candidates개
    찾아 [(위치, 매칭길이), ...]로 반환. 여러 매칭 후보를 모아 그중 가장 그럴듯한 문장을
    고르기 위한 것(아래 _score_sentence 참고) — 예전엔 첫 매칭에서 바로 멈췄다."""
    lowered = [(p, p.lower()) for p in phrases]
    low = tail.lower()
    found = []
    search_from = 0
    while len(found) < max_candidates:
        best = None
        for phrase, phrase_low in lowered:
            idx = low.find(phrase_low, search_from)
            if idx != -1 and (best is None or idx < best[0]):
                best = (idx, len(phrase))
        if best is None:
            break
        found.append(best)
        search_from = best[0] + best[1]
    return found


# "관계도 표에 뭘 하는지 안 보인다"는 피드백에 문장 경계 정리(위)로 가독성은 나아졌지만,
# 정확도 자체는 별개 문제였다 — 첫 매칭 문장이 실제 거래 내용이 아니라 Risk Factors의
# 경쟁사 나열이나 소송 상대 언급인 경우가 흔했다(실측: RDW 검색 시 BA/NOC 매칭이 전부
# "we compete against ... including Airbus" 같은 경쟁사 나열이었음). 여러 매칭 후보를
# 모아 아래 신호로 점수를 매기고 가장 그럴듯한 문장을 고른다 — 완벽한 분류가 아니라
# 근사 랭킹이라는 점은 여전하다.
_DEAL_KEYWORDS_RE = re.compile(
    r'\$[\d,.]+|\b\d{4}\b|\bagreements?\b|\bcontracts?\b|\bsupply\b|\bpartnerships?\b|'
    r'\bjoint ventures?\b|\bcollaborat\w*\b|\blicens\w*\b|\btask orders?\b|'
    r'\bpurchase orders?\b|\bmemorandum of understanding\b|\bacqui\w*\b|\bcustomers?\b|'
    r'\bvendors?\b|\bsubcontract\w*\b|\bmillion\b|\bbillion\b',
    re.IGNORECASE,
)
_NOISE_KEYWORDS_RE = re.compile(
    r'\bcompet\w*\b|\blawsuit\b|\bplaintiffs?\b|\bdefendants?\b|\bcomplaints?\b|'
    r'\balleg\w*\b|\blitigation\b',
    re.IGNORECASE,
)
# 문장 앞쪽 이 정도 범위 안에서 가장 최근에 나온 "Item N" 헤더를 찾아 그 섹션 안에 있다고
# 본다. 10-K/10-Q의 Item 1A(Risk Factors)·Item 3(Legal Proceedings)는 회사 이름이 실제
# 거래 내용과 무관하게(경쟁사 나열, 소송 상대) 자주 등장하는 섹션이라 감점한다. 헤더
# 형식이 필사마다 달라 완벽한 파서는 아니다 — 못 찾으면 그냥 감점 없이 넘어간다.
_ITEM_HEADER_RE = re.compile(r'\bItem\s+(\d+(?:\.\d+)?[A-Za-z]?)\b', re.IGNORECASE)
_NOISE_SECTION_ITEMS = {"1a", "3"}
_SECTION_LOOKBACK = 4000


def _section_penalty(tail, pos):
    window_text = tail[max(0, pos - _SECTION_LOOKBACK):pos]
    last_item = None
    for m in _ITEM_HEADER_RE.finditer(window_text):
        last_item = m.group(1).lower()
    return -3 if last_item in _NOISE_SECTION_ITEMS else 0


def _score_sentence(sentence, tail, pos):
    """문장이 실제 거래 내용을 설명할 가능성을 근사 점수화 — 여러 매칭 후보 중 하나를
    고르는 상대 비교용일 뿐, 절대적인 신뢰도 지표는 아니다."""
    score = len(_DEAL_KEYWORDS_RE.findall(sentence))
    score -= 2 * len(_NOISE_KEYWORDS_RE.findall(sentence))
    score += _section_penalty(tail, pos)
    return score


def _stream_find_context(url, phrases, window=260):
    """공시 문서를 스트리밍으로 받으며 phrases가 나오는 지점을 최대 _MAX_CANDIDATES개까지
    모아(최대 _CANDIDATE_SCAN_BYTES, 하나도 못 찾았으면 _MAX_FILING_BYTES까지 계속),
    그중 _score_sentence로 가장 그럴듯한 문장을 골라 반환한다. 못 찾으면 None.

    예전엔 첫 매칭에서 바로 멈췄는데, 그러면 실제 거래 내용이 아니라 아무 문맥이나
    뽑히기 쉬웠다(위 _score_sentence 설명 참조). 여러 후보를 모으려면 더 읽어야 해서
    예전보다 느리다 — 첫 매칭 지점에서 바로 끊던 것과 다른 트레이드오프."""
    if not phrases:
        return None

    tail = ""
    carry = ""
    total = 0
    occurrences = []

    try:
        with requests.get(
            url, headers={"User-Agent": _USER_AGENT}, timeout=15, stream=True,
        ) as r:
            # 멀티바이트 문자가 청크 경계에 걸쳐 깨지지 않도록 증분 디코더 사용
            decoder = codecs.getincrementaldecoder(r.encoding or "utf-8")(errors="ignore")
            for chunk in r.iter_content(chunk_size=_STREAM_CHUNK):
                if not chunk:
                    continue
                total += len(chunk)
                raw = carry + decoder.decode(chunk)
                cut = _safe_split_point(raw)
                carry = raw[cut:]
                tail += _clean_fragment(raw[:cut])

                occurrences = _find_all_occurrences(tail, phrases, _MAX_CANDIDATES)
                if len(occurrences) >= _MAX_CANDIDATES:
                    break
                if occurrences and len(tail) >= _CANDIDATE_SCAN_BYTES:
                    break
                if total > _MAX_FILING_BYTES:
                    break
    except Exception:
        return None

    if not occurrences:
        return None

    candidates = []
    for found_at, found_len in occurrences:
        start = max(0, found_at - window)
        end = min(len(tail), found_at + found_len + window)
        raw = tail[start:end]
        sentence, start_cut, end_cut = _trim_to_sentence(raw, found_at - start, found_len)
        if len(sentence) > _MAX_SENTENCE_CHARS:
            # 문장 하나가 너무 길면(법률 문서 특유의 장문) 단어 경계에서 자른다 — 그래도
            # 통째로 한 문장이라 예전 고정폭 절단보다는 훨씬 자연스럽게 끝난다. 말줄임표는
            # 아래에서 한 번만 붙이므로 여기서는 자르기만 한다(안 그러면 "…"가 두 번 붙음).
            sentence = sentence[:_MAX_SENTENCE_CHARS].rsplit(" ", 1)[0].rstrip(",;:")
            end_cut = True
        candidates.append((sentence, start_cut, end_cut, found_at))

    sentence, start_cut, end_cut, _pos = max(
        candidates, key=lambda c: _score_sentence(c[0], tail, c[3]),
    )
    prefix = "…" if start_cut else ""
    suffix = "…" if end_cut else ""
    return prefix + sentence + suffix


def _extract_context_snippet(url, company_name, window=260):
    """문서에서 회사명 주변 문맥을 뽑아 반환. 정식 법인명부터 순서대로 시도해 가장 구체적인
    표기를 우선 채택한다(검색 때 어떤 축약 단계로 매칭됐는지와 무관하게, 문서 안에 실제로
    적힌 표기를 그대로 쓰기 위함). 못 찾거나 실패하면 None."""
    key = (url, company_name)
    if key in _SNIPPET_CACHE:
        return _SNIPPET_CACHE[key]

    snippet = _stream_find_context(url, _filing_search_candidates(company_name), window)

    if len(_SNIPPET_CACHE) >= _SNIPPET_CACHE_MAX:
        for k in list(_SNIPPET_CACHE)[: _SNIPPET_CACHE_MAX // 5]:
            _SNIPPET_CACHE.pop(k, None)
    _SNIPPET_CACHE[key] = snippet
    return snippet


def attach_context_snippets(filing_edges, max_companies=_MAX_SNIPPET_COMPANIES):
    """filing_edges(find_filing_relationships 결과)를 상대 회사별로 묶어, 회사당 가장
    최근 엣지 1건에 대해서만 문서를 받아 문맥을 채운다(회사당 여러 건이어도 문서 1건만
    받아 대역폭 절약). 히트 수·최신순으로 정렬해 상위 max_companies개까지만 처리 —
    그래프에 표시되는 노드 수와 같은 개수다(_MAX_SNIPPET_COMPANIES 주석 참조).
    문맥을 못 얻은 엣지는 그대로 두어(수정 없이) 기존 일반 문구로 자연스럽게 폴백."""
    if not filing_edges:
        return filing_edges

    grouped = {}
    for e in filing_edges:
        g = grouped.setdefault(e["counterparty_ticker"], [])
        g.append(e)
    ranked = sorted(
        grouped.items(),
        key=lambda kv: (len(kv[1]), max(x.get("datetime") or 0 for x in kv[1])),
        reverse=True,
    )[:max_companies]

    targets = []
    for _, group_edges in ranked:
        latest_edge = max(group_edges, key=lambda e: e.get("datetime") or 0)
        targets.append(latest_edge)

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        futures = {
            executor.submit(
                _extract_context_snippet, e["url"], e.get("snippet_query_name", e["counterparty_name"]),
            ): e
            for e in targets
        }
        for future in as_completed(futures):
            edge = futures[future]
            snippet = future.result()
            if snippet:
                edge["context"] = snippet
    return filing_edges


# ---------------------------------------------------------------------------
# 단순 언급 승격 — 사용자 피드백: CoreWeave/IREN처럼 실제로는 공급·고객 관계로 보이는
# 회사가 전부 "공시 내 언급"(D등급, 기본 숨김)으로만 잡혀서 화면에 안 보이는 문제.
# attach_context_snippets()가 확보한 문맥(상위 _MAX_SNIPPET_COMPANIES개만 있음)에
# 거래 관련 키워드가 있고 노이즈 키워드(경쟁사 나열·소송)가 없으면, 구체적 관계 유형으로
# 승격해 기본 화면에 보이게 한다. 승격된 엣지는 등급 B(구조화된 문서 자체는 아니지만
# SEC 문맥에서 관계 가능성이 높음) — 여전히 방향은 unknown(문맥만으로 공급자/고객 중
# 누가 상대인지 확정할 수 없음).
# ---------------------------------------------------------------------------
_PROMOTION_TYPE_KEYWORDS = {
    "합작투자": re.compile(r"joint venture", re.IGNORECASE),
    "라이선싱": re.compile(r"licens\w*\s+agreement", re.IGNORECASE),
    "전략적 제휴": re.compile(
        r"strategic partnership|strategic alliance|collaboration agreement", re.IGNORECASE,
    ),
    "공급·고객 계약": re.compile(
        r"supply agreement|\bcustomers?\b|\bvendors?\b|\bsuppliers?\b|purchase orders?|"
        r"subcontract\w*",
        re.IGNORECASE,
    ),
}


def promote_mentions_with_context(filing_edges):
    """attach_context_snippets() 이후에 호출한다. "공시 내 언급" 엣지 중 실제 문맥을
    확보한 것만 검사해, 거래 관련 키워드가 있으면 구체적 관계 유형(등급 B)으로 승격하고,
    문맥이 없거나(상위 N개 밖) 노이즈 키워드가 함께 있으면 그대로 둔다(과확신보다 보수적
    판단을 우선). filing_edges를 그 자리에서 수정하고 그대로 반환한다."""
    for e in filing_edges:
        if e["relationship_type"] != "공시 내 언급":
            continue
        context = e.get("context")
        if not context or _NOISE_KEYWORDS_RE.search(context):
            continue
        promoted_type = next(
            (name for name, pattern in _PROMOTION_TYPE_KEYWORDS.items() if pattern.search(context)),
            None,
        )
        if promoted_type is None and _DEAL_KEYWORDS_RE.search(context):
            promoted_type = "공급·고객 계약"
        if promoted_type:
            e["relationship_type"] = promoted_type
            e["evidence_grade"] = "B"
            e["direction"] = "unknown"
    return filing_edges
