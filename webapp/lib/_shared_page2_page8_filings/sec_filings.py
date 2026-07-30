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

2026-07-27 추가: Schedule 13D/13G(대량 지분 보유)는 반대로 근거 등급 A — 구조화된 SEC
공식 문서에서 관계를 직접 명시하기 때문(추측이 아니라 문서에 적힌 그대로). 일반 언급
검색과 달리 최근 2년치만 조회하고 실패 시 조용히 빈 리스트를 반환한다
(find_beneficial_owners 참고).

2026-07-28: Exhibit 21 자회사 추출은 추가했다가 제거했다 — 대부분 지주회사·파이낸스
SPV라 투자 판단에 거의 안 쓰이는데(사용자 피드백), 회사당 최대 30개까지 그래프를
법인 구조로 도배해 실제로 의미 있는 관계(공급·고객, 지분 보유)를 압도해버렸다.
"""

import html
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta

import requests
import streamlit as st

from .filing_text import clean_fragment, stream_find_context

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
            search_direction, cp_ticker, cp_name, doc_cik = futures[future]
            hits, ambiguous = future.result()

            if search_direction == "forward":
                evidence_level = "공시 자료 (SEC EDGAR, 공식 문서)"
                snippet_name = cp_name
            else:
                evidence_level = "공시 자료 (상대 회사 공시에서 확인, SEC EDGAR)"
                snippet_name = target_name
            if ambiguous:
                evidence_level = "⚠️ 흔한 단어 검색이라 오탐 가능 · " + evidence_level

            for hit in hits:
                if search_direction == "forward":
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
                    # "forward"=이 문맥은 허브(target) 자신의 공시, "reverse"=상대 회사
                    # 자신의 공시 — 나중에 문맥에서 방향(공급자/고객 언어)을 판정할 때
                    # "누가 말하는 문장인지"를 알아야 허브 기준 방향으로 뒤집을 수 있다
                    # (아래 infer_relationship_direction 참고).
                    "search_direction": search_direction,
                    "ownership_pct": None,
                    "transaction_value": None,
                    "extraction_method": "mention",
                })
            done += 1
            if on_progress:
                on_progress(done, total)
    return edges


# ---------------------------------------------------------------------------
# 공시 첨부문서 목록 조회 — Schedule 13D/13G(아래)의 실제 문서를 찾는 데 쓰는 공용
# 유틸리티. (자회사 Exhibit 21 추출 기능은 사용자 판단상 투자 관점에서 가치가 낮고
# 그래프를 법인 구조로 도배해 제거함 — 이 함수와 아래 정규식들은 13D/13G에도 쓰여서 남음.)
# ---------------------------------------------------------------------------
_TR_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL | re.IGNORECASE)
_CELL_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.DOTALL | re.IGNORECASE)
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
        doc_type = clean_fragment(cells_html[3]).strip()
        if name:
            docs.append({"name": name, "type": doc_type})
    return docs


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
        cleaned = clean_fragment(r.text)
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
# 자본조달(유상증자·회사채 등록) 공시 — Company Events 페이지 보강 (2026-07-30).
# 사용자 피드백: 뉴스 기반 M&A/파트너십/경영진 교체만으론 내용이 빈약함. 유상증자를
# 영문 뉴스 키워드("public offering"/"secondary offering"/"private placement"...)로
# 잡으려 하면 표현이 제각각이라 재현율이 낮고 오탐도 늘어난다 — 대신 _list_13d_13g_filings
# 와 같은 "검색어 없이 폼타입으로 이 회사 관련 공시 전부"를 주는 방식을 재사용한다.
# S-1/S-3(등록)·424B*(등록에 따른 최종 투자설명서)는 등록 대상이 신주(유상증자)든
# 회사채든 같은 폼타입을 쓰므로, 폼타입 존재 자체가 "기업 재무" 신호로 충분하다.
# 8-K는 제외 — 폼타입만으로는 Item 번호(자본조달 관련 Item 3.02/2.03 여부)를 알 수 없어
# 대부분이 자본조달과 무관한 다른 사유(계약 체결·경영진 변경 등)라 오탐이 너무 커진다.
_CAPITAL_RAISE_FORMS = ("S-1", "S-3", "S-3ASR", "424B1", "424B2", "424B3", "424B4", "424B5")
_CAPITAL_RAISE_CATEGORY = "유상증자·자본조달"
_CAPITAL_RAISE_FORM_LABELS = {
    "S-1": "신규 증권 등록",
    "S-3": "간이 증권 등록(Shelf)",
    "S-3ASR": "간이 증권 등록(즉시효력, 대형사 전용)",
    "424B1": "투자설명서(공모 실행)",
    "424B2": "투자설명서(공모 실행)",
    "424B3": "투자설명서(공모 실행)",
    "424B4": "투자설명서(공모 실행)",
    "424B5": "투자설명서 보충(Shelf 공모 실행)",
}
_MAX_CAPITAL_RAISE_FILINGS = 15


def _list_capital_raise_filings(cik, lookback_days=365):
    """대상 CIK의 최근 lookback_days 안 S-1/S-3/424B* 공시 목록을 _list_13d_13g_filings와
    같은 방식(검색어 없는 폼타입별 Atom 피드)으로 가져온다. 폼타입이 8종이라 순차 호출
    대신 병렬로 가져온다."""
    if not cik:
        return []
    cutoff = date.today() - timedelta(days=lookback_days)

    def _fetch_one(form_type):
        try:
            r = requests.get(
                "https://www.sec.gov/cgi-bin/browse-edgar",
                params={
                    "action": "getcompany", "CIK": cik, "type": form_type,
                    "dateb": "", "owner": "include", "count": 40, "output": "atom",
                },
                headers={"User-Agent": _USER_AGENT}, timeout=10,
            )
            return r.text
        except Exception:
            return ""

    seen = set()
    filings = []
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        for text in executor.map(_fetch_one, _CAPITAL_RAISE_FORMS):
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
                    "form": _extract_pattern(_ATOM_FIELD_RES["type"], block),
                    "date": fdate,
                })
    filings.sort(key=lambda f: f.get("date") or "", reverse=True)
    return filings[:_MAX_CAPITAL_RAISE_FILINGS]


def find_capital_raise_filings(ticker, lookback_days=365):
    """티커의 S-1/S-3/424B* 공시를 Company Events 카드 형식(headline/source/datetime/url/
    categories)으로 반환한다. CIK를 못 찾거나 요청이 실패하면 조용히 빈 리스트 — "공시가
    없다"와 "확인 못 했다"를 화면에서 구분하진 않지만, 둘 다 과확신(허위 이벤트 표시)보다
    안전한 쪽으로 fail한다."""
    cik = get_cik(ticker)
    if not cik:
        return []
    try:
        filings = _list_capital_raise_filings(cik, lookback_days)
    except Exception:
        return []
    cik_no_padding = str(int(cik))
    results = []
    for f in filings:
        form = f["form"] or "?"
        accession_no_dashes = f["accession"].replace("-", "")
        url = (
            f"https://www.sec.gov/Archives/edgar/data/{cik_no_padding}/"
            f"{accession_no_dashes}/{f['accession']}-index.htm"
        )
        label = _CAPITAL_RAISE_FORM_LABELS.get(form, form)
        results.append({
            "headline": f"{form} 공시 — {label}",
            "source": "SEC EDGAR",
            "datetime": _file_date_to_epoch(f["date"]) if f.get("date") else None,
            "url": url,
            "summary": None,
            "categories": [{"category": _CAPITAL_RAISE_CATEGORY, "matched": [form]}],
        })
    return results


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
# 그래프는 이제 상대기업을 전부 다 그리지만(lib/charts.py), 회사마다 공시 원문을 받아
# 스니펫을 뽑는 건 시간이 걸려서(스트리밍이라 빨라도 요청 자체는 남음) 전체에 다 걸면
# 페이지가 느려진다. 근거가 가장 많은 상위 N개에만 실제 문맥을 채우고, 나머지는 요약
# 표에서 "원문 확인 필요" 안내로 자연스럽게 폴백된다(pages/8_관계도.py::_best_description).
_MAX_SNIPPET_COMPANIES = 10

# 스니펫 캐시 — 제출된 공시는 내용이 안 바뀌므로 (url, 회사명) → 스니펫은 영구히 유효하다.
# st.cache_data 대신 평범한 dict을 쓰는 이유는 워커 스레드에서 호출되기 때문(st.cache_data는
# 스크립트 실행 컨텍스트를 기대해서 ThreadPoolExecutor 워커에서 부르면 경고가 난다).
_SNIPPET_CACHE = {}
_SNIPPET_CACHE_MAX = 2000

# 공시 스트리밍 fetch·HTML 정리·문장 경계 자르기 같은 범용 텍스트 처리는
# lib/filing_text.py로 옮겼다(lib/financials.py의 경영진 코멘트 추출도 같은 로직이 필요해서
# 중복 구현하지 않기 위함, 2026-07-28). 여기 남은 건 "어떤 문장이 그럴듯한 관계 설명인가"를
# 판단하는 관계도 전용 스코어링뿐.

# "관계도 표에 뭘 하는지 안 보인다"는 피드백에 문장 경계 정리로 가독성은 나아졌지만,
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

# 임원·이사 경력 소개 문단 (2026-07-30, 실측: AMAT↔Shopify가 "공시 내 언급"으로 잡힘 —
# 실제로는 Shopify 이사 소개란에 "...previously served as Division CFO and in other
# financial leadership roles at Applied Materials, Visa, and United Technologies"였다).
# 이런 문단은 회사 간 관계를 전혀 설명하지 않는데도(그냥 한 사람의 과거 직장 나열)
# _NOISE_KEYWORDS_RE(경쟁사·소송)에는 안 걸려서 그대로 "공시 내 언급"으로 노출된다.
# 관계도 표에 뜨는 다른 노이즈(경쟁사 나열 등)는 그나마 "두 회사가 같은 업계"라는 정보는
# 있지만, 경력 소개는 그 회사 자체와도 무관해서 승격 차단만으론 부족하다 — 아예 목록에서
# 빼야 한다(drop_biographical_mentions 참고).
_BIOGRAPHICAL_MENTION_RE = re.compile(
    r'\bage\s+\d{2}\b|'
    r'\bprior to joining\b|'
    r'\bpreviously served\b|'
    r'\b(?:has been|is)\s+a\s+member of\s+(?:our|the)\s+[Bb]oard\b|'
    r'\bleadership roles?\s+at\b|'
    r'\bserved as\b(?:\s+\S+){0,10}?\s+Chief\s+\w+\s+Officer\b|'
    r'\bspent\s+(?:more than\s+)?(?:a\s+decade|\d+\s+years?)\s+in\s+',
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
    # 같은 문서 안에 임원 경력 소개 말고 다른 후보 문장이 있으면(예: 이사 소개란과 별개로
    # 실제 거래를 설명하는 문장도 있는 회사) 그쪽이 더 높은 점수를 받도록 감점만 해두고
    # 완전히 배제하지는 않는다 — 완전 배제는 drop_biographical_mentions()가 담당(문서
    # 전체에 경력 소개 문장뿐인 경우까지 걸러내려면 스코어링만으론 부족하기 때문).
    if _BIOGRAPHICAL_MENTION_RE.search(sentence):
        score -= 2
    score += _section_penalty(tail, pos)
    return score


def _extract_context_snippet(url, company_name, window=260):
    """문서에서 회사명 주변 문맥을 뽑아 반환. 정식 법인명부터 순서대로 시도해 가장 구체적인
    표기를 우선 채택한다(검색 때 어떤 축약 단계로 매칭됐는지와 무관하게, 문서 안에 실제로
    적힌 표기를 그대로 쓰기 위함). 못 찾거나 실패하면 None."""
    key = (url, company_name)
    if key in _SNIPPET_CACHE:
        return _SNIPPET_CACHE[key]

    snippet = stream_find_context(
        url, _filing_search_candidates(company_name),
        score_sentence=_score_sentence, user_agent=_USER_AGENT, window=window,
    )

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


def drop_biographical_mentions(filing_edges):
    """attach_context_snippets() 다음, promote_mentions_with_context() 전에 호출한다.
    문맥이 임원·이사 경력 소개(_BIOGRAPHICAL_MENTION_RE)로 판정된 상대회사는 그 회사와
    관련된 엣지 전부를 목록에서 뺀다 — 문맥을 확보한 엣지(회사당 1건, attach_context_
    snippets 참고) 하나만 지우면 같은 회사의 다른 날짜 언급이 문맥 없이 남아 "공시 내
    언급 포함" 토글에서 여전히 보이므로, 그 회사 자체를 후보에서 제외한다. 승격 차단
    (promote_mentions_with_context의 _BIOGRAPHICAL_MENTION_RE 점수 감점)과 달리 이건
    D등급 "공시 내 언급"으로도 노출을 안 시킨다 — 경력 소개는 두 회사 관계에 대해 아무
    신호도 안 주기 때문(경쟁사 나열처럼 "같은 업계"라는 정보조차 없음)."""
    biographical_tickers = {
        e["counterparty_ticker"] for e in filing_edges
        if e.get("context") and _BIOGRAPHICAL_MENTION_RE.search(e["context"])
    }
    if not biographical_tickers:
        return filing_edges
    return [e for e in filing_edges if e["counterparty_ticker"] not in biographical_tickers]


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
    # M&A는 "acquisition/merger" 문구가 있어도 그 뒤 문장에 customer/vendor 같은 일반
    # 거래 단어가 같이 나오는 경우가 흔해서(예: 피인수회사의 매출·고객 설명), M&A 판정을
    # 공급·고객 계약보다 먼저 검사해야 오분류를 막는다(실측: "completed the acquisition
    # of..."가 M&A 대신 공급·고객 계약으로 잘못 승격되던 문제).
    "M&A": re.compile(
        r"\bmerger\b|\bacqui(?:re|res|red|ring|sition)\w*\b|\btender offer\b|"
        r"\bbusiness combination\b",
        re.IGNORECASE,
    ),
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


# ---------------------------------------------------------------------------
# 방향 판정 (2026-07-28 신규) — "공급·고객 계약"으로 승격돼도 지금까지는 direction이
# 항상 "unknown"이라 화살표도 안 뜨고 hover에서도 "누가 누구에게 파는지" 안 보인다는
# 문제(사용자 피드백: "hover만 보고 관계를 바로 알 수 있어야 하고, 사용자는 최소한의
# 노력만 해야 한다"). 문맥(context)에 공급자 언어/고객 언어 중 뭐가 있는지 보고,
# 그 문맥이 허브 자신의 공시(forward)인지 상대 회사 자신의 공시(reverse)인지와 조합해
# 허브 기준 방향(outbound=허브→상대, inbound=상대→허브)으로 뒤집는다.
#
# 실측 검증(EveryTie NVIDIA 페이지의 공개 인용문 2건으로 확인):
#   - NVDA 자신의 8-K(forward), "...large-scale deployment of NVIDIA ... GPUs" →
#     고객 언어("deployment of") 매칭 → forward이므로 outbound(NVDA→상대) — 맞음.
#   - Gigabyte 자신의 연차보고서(reverse, 상대=Gigabyte), "Primary source of supply
#     ... NVIDIA ..." → 공급자 언어("primary source of supply") 매칭 → reverse이므로
#     outbound(NVDA가 Gigabyte에 공급) — 맞음(Gigabyte 입장에서 NVIDIA는 "공급원"이므로
#     허브 NVIDIA 기준으로는 자신이 공급하는 쪽).
#
# 공급자 언어/고객 언어가 둘 다 없거나 둘 다 있으면(모순) "unknown"으로 남긴다 — 근거가
# 명확할 때만 판정하고 애매하면 추측하지 않는다는 원칙(원칙 7) 유지.
#
# 2026-07-28 재현율 개선: 초판은 "purchase ... from"처럼 동사 바로 뒤에 정해진 명사가
# 붙어야만 잡혔다(실측: "purchase certain raw materials from X"가 "raw materials"라는
# 수식어 때문에 안 잡힘 — 합성 표본 20건 중 15건이 방향 unknown으로 남는 문제로 확인됨).
# 동사와 전치사(from/to) 사이에 최대 5단어까지 아무 단어나 끼어도 잡히게 (?:\S+\s+){0,N}
# 형태로 느슨하게 바꿨다 — 문장이 지나치게 길면(다른 절로 넘어가면) 그래도 안 잡히므로
# 여전히 과매칭 위험은 낮다.
_SUPPLIER_LANGUAGE_RE = re.compile(
    r"our supplier|supplied by|"
    r"(?:purchase[sd]?|buy(?:s)?|bought)\s+(?:\S+\s+){0,5}?(?:from|with)\b|"
    r"sole source|single source|primary source of supply|our vendor|"
    r"rel(?:y|ies|ying|ied)\s+(?:\S+\s+){0,3}?on\b|"
    r"depend(?:s|ent|ing)?\s+(?:\S+\s+){0,3}?on\b|"
    r"licen[sc]e[sd]?\s+(?:\S+\s+){0,5}?from\b|"
    # "subcontract 작업을 X에게 준다" = X가 그 일을 대신 해준다는 뜻이라, 문법적으로는
    # "...to"(고객 언어처럼 보임)지만 의미상 반대(X가 우리에게 서비스를 공급) — 그래서
    # 고객 언어가 아니라 여기(공급자 언어)에 둔다. 사용자 질문으로 발견된 케이스.
    r"subcontract\w*\s+(?:\S+\s+){0,6}?to\b",
    re.IGNORECASE,
)
_CUSTOMER_LANGUAGE_RE = re.compile(
    r"suppl(?:y|ies|ied)\s+(?:\S+\s+){0,6}?to\b|"
    r"(?:sold|sells?|selling)\s+(?:\S+\s+){0,3}?to\b|"
    r"customers?\s+includ\w*|our customer\b|deploy(?:ment|ed|s)?\s+of|"
    r"provide[sd]?\s+(?:\S+\s+){0,6}?to\b|"
    r"licen[sc]e[sd]?\s+(?:\S+\s+){0,5}?to\b",
    re.IGNORECASE,
)


def infer_relationship_direction(context, search_direction):
    """context(공시 원문에서 뽑은 발췌문)와 search_direction("forward"=허브 자신의
    공시에서 찾음, "reverse"=상대 회사 자신의 공시에서 찾음)을 조합해 허브 기준 방향을
    반환한다. 공급자 언어와 고객 언어가 동시에 없거나(0,0) 동시에 있으면(모순) 판정을
    포기하고 "unknown"을 반환 — 한쪽만 뚜렷하게 걸릴 때만 판정한다."""
    if not context or not search_direction:
        return "unknown"
    is_supplier_lang = bool(_SUPPLIER_LANGUAGE_RE.search(context))
    is_customer_lang = bool(_CUSTOMER_LANGUAGE_RE.search(context))
    if is_supplier_lang == is_customer_lang:
        return "unknown"
    if search_direction == "forward":
        return "outbound" if is_customer_lang else "inbound"
    return "outbound" if is_supplier_lang else "inbound"


# 부정 가드 (2026-07-28 신규) — "No single customer accounted for more than 10% of
# our revenue" 같은 부정문은 오히려 "집중 위험이 없다"는 뜻인데, _DEAL_KEYWORDS_RE는
# "customers"라는 단어만 보고 그대로 승격시켜버린다(사용자 질문으로 발견된 케이스).
# "no/not/none ... (customer/supplier/vendor) ... (more than/accounted for/represented)"
# 형태를 잡아 이 문장은 애초에 승격하지 않는다 — EveryTie 방법론의 negation guard와
# 같은 발상("no customer accounted for more than 10%"는 집중의 반대 의미).
_NEGATION_GUARD_RE = re.compile(
    r"\b(?:no|not|none|neither)\b(?:\s+\S+){0,6}?\s+"
    r"(?:customer|supplier|vendor)s?\b(?:\s+\S+){0,8}?\s+"
    r"(?:more than|accounted for|represented|exceed(?:ed|s)?)",
    re.IGNORECASE,
)

# 제3자 관계 가드 (2026-07-30, 실측: NVDA↔AMD가 "전략적 제휴"로 잘못 승격됨) — AMD 10-Q의
# Risk Factors에서 실제 텍스트를 확인해보니 "Similarly, Nvidia ... leverages its market
# position ... For example, in September 2025, Nvidia announced a partnership and
# investment in Intel"이었다. 검색어(허브 이름 "NVIDIA")와 거래 키워드("partnership")는
# 둘 다 문장에 있어 기존 로직은 승격시켰지만, 실제 그 거래의 당사자는 Nvidia와 Intel이지
# AMD(문맥을 검색한 대상 회사)가 아니다 — AMD는 그저 "경쟁사끼리 제휴가 늘고 있다"는
# 문맥에서 예시로 언급됐을 뿐이다.
#
# 이런 문장은 검색 대상 회사 자신이 그 거래의 당사자로 등장하지 않는다는 공통점이 있다 —
# reverse 검색(상대 회사 자신의 공시에서 허브 이름을 찾음)이면 그 공시 주인(상대 회사)이,
# forward 검색(허브 자신의 공시에서 상대 이름을 찾음)이면 허브 자신이 "we/our/the Company"
# 같은 자기지칭이나 자기 회사명으로 그 문장에 등장해야 한다. 둘 다 없으면 "누구 얘기인지도
# 모르는 채 거래 키워드만 보고" 승격시키는 셈이라 보수적으로 승격을 거부한다(과확신보다
# 보수적 판단 우선 원칙, 이 함수 docstring 참고).
_SELF_REFERENCE_PRONOUNS_RE = re.compile(r"\b(?:we|our|us|the Company)\b", re.IGNORECASE)

# 실측(AMAT 10-K) 재현: 위 가드를 처음 넣고 보니 진짜 관계까지 같이 걸러졌다 —
#   - "Received a 2026 Intel EPIC Supplier Award" (Applied's EPIC Center 문단 안) — 회사가
#     자기 자신을 정식명("Applied Materials") 대신 축약형("Applied")으로 부름.
#   - "Applied and Micron Technology are working to develop next-generation DRAM..." — 역시
#     "Applied"만 등장.
#   - "Percentage of Net Revenue Taiwan Semiconductor Manufacturing Company Limited 18%" —
#     재무제표 매출 비중표는 애초에 문장 형태가 아니라 주어(자기지칭)가 없다. 하지만 이
#     표는 정의상 항상 "이 공시를 낸 회사 자신의" 매출 비중이라 굳이 자기지칭이 없어도
#     안전하게 자기 관계로 인정할 수 있다.
# 그래서 두 가지를 보강한다: (1) 매출 비중표 패턴은 자기지칭 없이도 통과, (2) 회사명 첫
# 단어(대문자 그대로, 5자 이상)도 자기지칭으로 인정 — "as applied research"처럼 소문자로
# 쓰인 일반 단어 오탐은 대소문자 구분(대문자 시작만 매칭)으로 줄인다.
_REVENUE_CONCENTRATION_TABLE_RE = re.compile(r"percentage\s+of\s+(?:net\s+)?revenue", re.IGNORECASE)


def _self_reference_present(context, self_name):
    """context 안에 자기지칭 대명사·회사명(정식/축약형)·매출 비중표 패턴이 등장하는지."""
    if _SELF_REFERENCE_PRONOUNS_RE.search(context) or _REVENUE_CONCENTRATION_TABLE_RE.search(context):
        return True
    for phrase in _filing_search_candidates(self_name):
        if phrase and re.search(r"\b" + re.escape(phrase) + r"\b", context, re.IGNORECASE):
            return True
    first_word = (self_name or "").split()[0].rstrip(",") if self_name else ""
    if len(first_word) >= 5 and re.search(r"\b" + re.escape(first_word) + r"\b", context):
        return True
    return False


def promote_mentions_with_context(filing_edges, hub_name):
    """attach_context_snippets() 이후에 호출한다. "공시 내 언급" 엣지 중 실제 문맥을
    확보한 것만 검사해, 거래 관련 키워드가 있으면 구체적 관계 유형(등급 B)으로 승격하고,
    문맥이 없거나(상위 N개 밖) 노이즈 키워드·부정 가드·제3자 가드가 함께 있으면 그대로
    둔다(과확신보다 보수적 판단을 우선). 승격된 건은 전부 infer_relationship_direction()으로
    방향도 시도한다 — "전략적 제휴"라고 분류돼도 실제 문맥은 "OO에 제품을 대규모 공급"처럼
    방향이 뚜렷한 경우가 흔하다(실측: NVDA-Meta 8-K, 문구는 "strategic partnership"이지만
    내용은 "large-scale deployment of NVIDIA ... GPUs"). 공급자/고객 언어가 뚜렷하지 않으면
    infer_relationship_direction()이 알아서 "unknown"을 반환하므로, 유형별로 시도 여부를
    가르지 않고 전부 통과시켜도 안전하다. filing_edges를 그 자리에서 수정하고 그대로
    반환한다.

    hub_name: 이 관계도의 허브 기업명 — forward 검색(허브 자신의 공시)일 때 제3자 가드의
    자기지칭 대상이 된다(reverse는 엣지 자신의 counterparty_name을 쓴다)."""
    for e in filing_edges:
        if e["relationship_type"] != "공시 내 언급":
            continue
        context = e.get("context")
        if not context or _NOISE_KEYWORDS_RE.search(context) or _NEGATION_GUARD_RE.search(context):
            continue
        self_name = hub_name if e.get("search_direction") == "forward" else e.get("counterparty_name")
        if not _self_reference_present(context, self_name):
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
            e["direction"] = infer_relationship_direction(context, e.get("search_direction"))
    return filing_edges
