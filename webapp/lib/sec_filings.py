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
본문에 등장하는지"로 검색한다. 대신 정밀 관계 유형·방향성은 알 수 없음 — "공시상 언급"
까지만 표시하고, 실제 문맥은 사용자가 링크를 눌러 원문에서 직접 확인해야 한다(과확신 방지).
"""

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
                    "relationship_type": "공시상 언급",
                    "status": "공시 확인",
                    "evidence_level": evidence_level,
                    "headline": headline,
                    "url": _filing_url(doc_cik, hit),
                    "datetime": _file_date_to_epoch(hit["file_date"]),
                    "snippet_query_name": snippet_name,
                })
            done += 1
            if on_progress:
                on_progress(done, total)
    return edges


# ---------------------------------------------------------------------------
# 문맥 추출 — 검색 API는 스니펫을 안 줘서(실측 확인), 문서 원문을 받아 회사명 주변을
# 직접 잘라낸다. re + html(둘 다 표준 라이브러리)만 사용 — 새 의존성 없음.
# ---------------------------------------------------------------------------
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_ANY_TAG_RE = re.compile(r"<[^>]+>")
_MAX_SNIPPET_COMPANIES = 20


@st.cache_data(ttl=2592000, show_spinner=False)
def _fetch_filing_text(url):
    """공시 문서 원문을 받아 태그 제거 + 엔티티 디코딩한 순수 텍스트로 반환. 제출된
    공시는 내용이 안 바뀌므로 30일 캐시(검색 인덱스 캐시보다 훨씬 길게 잡아도 안전).
    실패 시 빈 문자열(다른 lib 함수들과 동일한 조용한 실패 패턴)."""
    try:
        r = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=15)
        text = _SCRIPT_STYLE_RE.sub(" ", r.text)
        text = _ANY_TAG_RE.sub(" ", text)
        text = html.unescape(text)
        return re.sub(r"\s+", " ", text).strip()
    except Exception:
        return ""


def _extract_context_snippet(url, company_name, window=180):
    """문서 원문에서 회사명이 등장하는 위치 주변 ±window자를 잘라 반환. 정식명부터
    순서대로 시도해 가장 구체적인 문맥을 우선 채택(검색 때 어떤 단계로 매칭됐는지와
    무관하게, 문서 안에서 실제로 찾을 수 있는 표기를 그대로 씀). 못 찾으면 None."""
    text = _fetch_filing_text(url)
    if not text:
        return None
    text_lower = text.lower()
    for phrase in _filing_search_candidates(company_name):
        idx = text_lower.find(phrase.lower())
        if idx == -1:
            continue
        start = max(0, idx - window)
        end = min(len(text), idx + len(phrase) + window)
        prefix = "…" if start > 0 else ""
        suffix = "…" if end < len(text) else ""
        return prefix + text[start:end].strip() + suffix
    return None


def attach_context_snippets(filing_edges, max_companies=_MAX_SNIPPET_COMPANIES):
    """filing_edges(find_filing_relationships 결과)를 상대 회사별로 묶어, 회사당 가장
    최근 엣지 1건에 대해서만 문서를 받아 문맥을 채운다(회사당 여러 건이어도 문서 1건만
    받아 대역폭 절약). 히트 수·최신순으로 정렬해 상위 max_companies개까지만 처리 —
    그래프에 어차피 상위 10개만 표시되므로(MAX_RELATIONSHIP_NODES) 여유 있게 20개.
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
