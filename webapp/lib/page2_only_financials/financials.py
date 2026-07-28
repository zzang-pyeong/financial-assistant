"""재무제표 정량 지표(yfinance) + (있으면) 경영진 코멘트 인용.

이 프로젝트 전체의 데이터 신뢰성 원칙(docs/PRD.md — "확실하지 않은 필드는 추측해 채우지
않고 미확인으로 남긴다")을 그대로 따른다: 코멘트는 실제로 8-K/뉴스에서 찾은 문장만 인용하고,
없으면 빈 리스트를 반환한다 — 항목당 "N개 이유"를 억지로 채우지 않는다.

실측 검증(2026-07-28, 이 기능 설계 중 직접 확인):
- 10-K MD&A는 CapEx가 큰 회사(NVIDIA/Micron)조차 "we spent $6.1B... to support future growth"류
  상투어뿐, 구체적 이유가 없었다.
- NVIDIA가 실적발표 8-K에 첨부하는 CFO Commentary(EX-99.2)는 매출/마진/영업비용 등 항목별로
  "driven by / primarily due to" 형태의 구체적 설명을 담고 있었다 — 단, 모든 회사가 이런
  문서를 내는 건 아니라서(Micron은 보도자료뿐) 어느 첨부문서인지 파일명으로 구분하지 않고
  8-K의 모든 첨부문서를 동일하게 스캔한다.
- 뉴스는 단순 "capex" 키워드만으로는 "AI 캐펙스가 버블이냐" 류 오피니언 칼럼이 대부분이었다.
  금액/시설명 + 발표성 동사 조합으로 좁히면 노이즈는 줄지만 재현율도 낮아진다(대부분의
  회사·기간은 매치가 없는 게 정상) — 그래서 8-K에서 못 찾았을 때만 보충하는 2순위로 둔다.
"""

import re
from datetime import date, datetime, timedelta

import requests
import streamlit as st

from lib._shared_core.data import get_finnhub_company_news
from lib._shared_page2_page8_filings.filing_text import stream_find_context
from lib._shared_core.page_helpers import news_date_str
from lib._shared_core.qualitative import is_relevant
from lib._shared_page2_page8_filings.sec_filings import _list_filing_documents, get_cik

_USER_AGENT = "EnterTicker research contact@example.com"

# ---------------------------------------------------------------------------
# 정량 지표 — yfinance income_stmt/cashflow에서 항목 추출 (실측: NVDA 기준 행 이름 확인)
# ---------------------------------------------------------------------------


def _row(df, *names):
    """df(yfinance statement DataFrame)에서 names 중 처음 매칭되는 행을
    {period_end(Timestamp): value} dict으로. 못 찾거나 df가 비어있으면 None.
    NaN 값(그 기간 항목 자체가 없음)은 제외 — 지어내지 않는다."""
    if df is None or df.empty:
        return None
    for name in names:
        if name in df.index:
            series = df.loc[name].dropna()
            if series.empty:
                continue
            return {idx: float(v) for idx, v in series.items()}
    return None


def revenue_series(income_stmt):
    return _row(income_stmt, "Total Revenue", "Operating Revenue")


def gross_margin_series(income_stmt):
    revenue = revenue_series(income_stmt)
    gross_profit = _row(income_stmt, "Gross Profit")
    if not revenue or not gross_profit:
        return None
    return {p: v / revenue[p] for p, v in gross_profit.items() if p in revenue and revenue[p]}


def operating_margin_series(income_stmt):
    revenue = revenue_series(income_stmt)
    op_income = _row(income_stmt, "Operating Income")
    if not revenue or not op_income:
        return None
    return {p: v / revenue[p] for p, v in op_income.items() if p in revenue and revenue[p]}


def net_income_series(income_stmt):
    return _row(income_stmt, "Net Income")


def capex_series(cashflow):
    """CapEx 절대값(양수)으로 반환 — yfinance는 현금유출 관례상 음수로 준다(실측 확인)."""
    raw = _row(cashflow, "Capital Expenditure", "CapitalExpenditure")
    if not raw:
        return None
    return {p: abs(v) for p, v in raw.items()}


def operating_cash_flow_series(cashflow):
    return _row(cashflow, "Operating Cash Flow")


def free_cash_flow_series(cashflow):
    """yfinance가 이미 'Free Cash Flow' 행을 주면 그대로 쓰고(Yahoo 자체 계산 신뢰),
    없을 때만 OCF - CapEx로 직접 계산(둘 다 있는 기간만 — 지어내지 않는다)."""
    fcf = _row(cashflow, "Free Cash Flow")
    if fcf:
        return fcf
    ocf = operating_cash_flow_series(cashflow)
    capex = capex_series(cashflow)
    if not ocf or not capex:
        return None
    return {p: v - capex[p] for p, v in ocf.items() if p in capex}


def capex_pct_revenue(capex, revenue):
    """두 시리즈 다 있는 기간만 비율 계산."""
    if not capex or not revenue:
        return None
    return {p: v / revenue[p] for p, v in capex.items() if p in revenue and revenue[p]}


# ---------------------------------------------------------------------------
# 경영진 코멘트 1순위 — 실적발표 8-K(보도자료·CFO Commentary 등 첨부문서 전부를 동일하게
# 스캔 — 어느 게 상세 문서인지는 회사마다 명명 규칙이 달라 파일명으로 구분하지 않는다)
# ---------------------------------------------------------------------------

METRIC_PHRASES = {
    "revenue": ["revenue increased", "revenue decreased", "revenue was", "revenue grew"],
    "gross_margin": ["gross margin"],
    "operating_margin": ["operating income", "operating expenses"],
    "net_income": ["net income"],
    "capex": ["capital expenditures", "capital expenditure"],
    "free_cash_flow": ["free cash flow"],
}

# 실측(이 기능 설계 중 확인)상 진짜 설명 문장은 이런 연결어를 동반하는 경우가 많고,
# Risk Factors류 보일러플레이트는 이런 상투 문구로 걸러진다.
_SIGNAL_RE = re.compile(
    r"\bprimarily due to\b|\bdriven by\b|\bas a result of\b|\battributable to\b|"
    r"\bprimarily related to\b|\bprimarily reflect(?:s|ing)?\b|\bmainly due to\b",
    re.IGNORECASE,
)
_RISK_BOILERPLATE_RE = re.compile(
    r"\bdo not (?:currently )?anticipate\b|\bcould have a material adverse effect\b|"
    r"\bcompetitors may increase\b|\bmay require\b|\bcould necessitate\b|"
    r"\bwe do not currently\b|"
    # 실측(이 기능 설계 중 발견): 표 오탐을 걸러내고 나면 그다음으로 자주 걸리는 게
    # "우리는 이 비GAAP 지표를 이렇게 정의한다"류 회계 용어 정의 문단(Micron/Salesforce
    # 8-K에서 실제로 재현) — 실제 원인 설명이 아니라 용어 설명일 뿐이라 같이 걸러낸다.
    r"\bdefines? the non-gaap measure\b|\brepresents gaap\b|\breconciliations? (?:of|between)\b|"
    r"\bmanagement excludes\b",
    re.IGNORECASE,
)

# 실측(이 기능 설계 중 발견): 실적발표 첨부문서의 재무제표 표(HTML table)가 태그 제거 후
# 문장부호 없는 숫자 나열로 평평해지면, 문장 경계 탐색이 그걸 통째로 "한 문장"으로 오인해
# "39.8 % 22.4 % 40.9 % ... Operating expenses 5,103 4,309" 같은 걸 인용문으로 뽑아버렸다
# (Micron/Salesforce 8-K에서 실제로 재현됨) — 숫자 토큰 밀도가 비정상적으로 높으면 표로
# 간주해 걸러낸다. 정상적인 설명 문장도 숫자를 몇 개는 포함하지만("record $62.3 billion,
# up 22%... up 75%"는 숫자 3개), 표는 훨씬 조밀하다.
_NUMBER_TOKEN_RE = re.compile(r"\d[\d,]*\.?\d*")
_TABLE_DUMP_NUMBER_THRESHOLD = 6

_MAX_DOCS_PER_FILING = 6


def _looks_like_table_dump(sentence):
    """숫자 토큰이 너무 조밀하면(재무제표 표가 통째로 한 '문장'으로 잘못 뽑힌 경우)
    실제 서술형 문장이 아니라고 판단한다."""
    return len(_NUMBER_TOKEN_RE.findall(sentence)) >= _TABLE_DUMP_NUMBER_THRESHOLD


def _score_financial_sentence(sentence, tail, pos):
    """관계도의 _score_sentence(lib/sec_filings.py)와 같은 발상이지만, 재무 항목
    서술에 맞는 신호어/보일러플레이트/표-오탐 신호로 자체 점수화."""
    score = 2 if _SIGNAL_RE.search(sentence) else 0
    score -= 3 if _RISK_BOILERPLATE_RE.search(sentence) else 0
    score -= 6 if _looks_like_table_dump(sentence) else 0
    return score


@st.cache_data(ttl=86400, show_spinner=False)
def _list_recent_8k(cik, lookback_days=730):
    """cik의 최근 8-K 목록(accession, 신고일)을 가져온다. 실패 시 빈 리스트."""
    if not cik:
        return []
    try:
        r = requests.get(
            f"https://data.sec.gov/submissions/CIK{cik}.json",
            headers={"User-Agent": _USER_AGENT}, timeout=15,
        )
        payload = r.json()
    except Exception:
        return []
    recent = payload.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    cutoff = date.today() - timedelta(days=lookback_days)
    out = []
    for i, form in enumerate(forms):
        if form != "8-K":
            continue
        try:
            fdate = datetime.strptime(dates[i], "%Y-%m-%d").date()
        except (ValueError, IndexError):
            continue
        if fdate < cutoff:
            continue
        out.append({"accession": accessions[i], "date": fdate})
    return out


def _nearest_8k(cik, period_end_date):
    """period_end_date(회계기간 종료일) 이후 가장 가까운 8-K를 고른다(실적 8-K는 보통
    기간 종료 몇 주~두 달 뒤 발표) — 못 찾으면 None."""
    candidates = [f for f in _list_recent_8k(cik) if f["date"] >= period_end_date]
    if not candidates:
        return None
    return min(candidates, key=lambda f: f["date"])


# (url, metric_key) → 스니펫. 제출된 공시는 내용이 안 바뀌므로 영구 캐시 —
# lib/sec_filings.py의 _SNIPPET_CACHE와 같은 패턴(워커 스레드에서도 안전한 평범한 dict).
_COMMENTARY_CACHE = {}
_COMMENTARY_CACHE_MAX = 500


def find_earnings_commentary(ticker, metric_key, period_end_date, max_quotes=3):
    """해당 회계기간과 가장 가까운 실적 8-K의 첨부문서에서 metric_key 관련 문장을 최대
    max_quotes개 찾는다. 8-K를 못 찾거나 문장을 못 찾으면 빈 리스트 — 개수를 강제하지
    않는다."""
    phrases = METRIC_PHRASES.get(metric_key)
    if not phrases:
        return []
    cik = get_cik(ticker)
    if not cik:
        return []
    filing = _nearest_8k(cik, period_end_date)
    if not filing:
        return []

    accession = filing["accession"]
    cik_nopad = str(int(cik))
    accession_nodash = accession.replace("-", "")
    docs = [
        d for d in _list_filing_documents(cik, accession)
        if (d.get("name") or "").lower().endswith((".htm", ".html"))
    ][:_MAX_DOCS_PER_FILING]

    quotes = []
    for doc in docs:
        url = f"https://www.sec.gov/Archives/edgar/data/{cik_nopad}/{accession_nodash}/{doc['name']}"
        cache_key = (url, metric_key)
        if cache_key in _COMMENTARY_CACHE:
            snippet = _COMMENTARY_CACHE[cache_key]
        else:
            snippet = stream_find_context(
                url, phrases, score_sentence=_score_financial_sentence,
                user_agent=_USER_AGENT, max_candidates=4,
            )
            if len(_COMMENTARY_CACHE) >= _COMMENTARY_CACHE_MAX:
                for k in list(_COMMENTARY_CACHE)[: _COMMENTARY_CACHE_MAX // 5]:
                    _COMMENTARY_CACHE.pop(k, None)
            _COMMENTARY_CACHE[cache_key] = snippet

        if snippet and not _RISK_BOILERPLATE_RE.search(snippet) and not _looks_like_table_dump(snippet):
            quotes.append({
                "quote": snippet, "source_kind": "SEC 8-K",
                "url": url, "date": filing["date"].isoformat(),
            })
        if len(quotes) >= max_quotes:
            break
    return quotes


# ---------------------------------------------------------------------------
# 경영진 코멘트 2순위 — 뉴스 (8-K에서 못 찾았을 때만 보충, capex만 우선 지원)
# ---------------------------------------------------------------------------

_CAPEX_NEWS_KEYWORDS = [
    "capital expenditure", "capex", "capacity expansion", "breaks ground",
    "new fab", "new plant", "new factory", "data center investment",
    "billion investment", "manufacturing facility",
]
# 실측(이 기능 설계 중 검증): 단순 키워드 매칭은 "AI 캐펙스 버블 논쟁" 류 오피니언 칼럼이
# 대부분이었다. 금액 또는 시설명이 발표성 동사와 함께 있어야 하고, 오피니언 문구가 있으면
# 제외해야 실제 발표 기사만 걸러진다(관계도의 _looks_like_market_roundup과 같은 발상).
_MONEY_RE = re.compile(r"\$[\d,.]+\s*(?:billion|million|B|M)\b", re.IGNORECASE)
_FACILITY_RE = re.compile(
    r"\b(?:campus|plant|factory|fab|facility|data\s?center|headquarters|hq)\b", re.IGNORECASE,
)
_ANNOUNCE_VERB_RE = re.compile(
    r"\b(?:announces?|announced|to invest|plans? to invest|planned|breaks ground|"
    r"unveils?|to build|will build|to construct)\b", re.IGNORECASE,
)
_OPINION_RE = re.compile(
    r"\b(?:should investors|is bogus|avoid|stays? hold|bold predictions?|buy this week|"
    r"warning|reasons?|scare|arms race|debate|beneficiaries)\b", re.IGNORECASE,
)


def find_capex_news(ticker, company_name, lookback_days=270, max_items=2):
    """CapEx 관련 뉴스 중 (금액 또는 시설명) AND 발표성 동사가 있고 오피니언 문구가 없는
    기사만 통과시킨다. 대부분의 회사·기간은 매치가 없는 게 정상 — 없으면 빈 리스트."""
    today = date.today()
    news = get_finnhub_company_news(
        ticker, (today - timedelta(days=lookback_days)).isoformat(), today.isoformat(),
    )
    if not news:
        return []

    results = []
    for n in news:
        if not is_relevant(n, ticker, company_name):
            continue
        text = f"{n.get('headline') or ''} {n.get('summary') or ''}"
        has_keyword = any(
            re.search(r"\b" + re.escape(kw) + r"\b", text, re.IGNORECASE)
            for kw in _CAPEX_NEWS_KEYWORDS
        )
        if not has_keyword:
            continue
        has_money_or_facility = bool(_MONEY_RE.search(text) or _FACILITY_RE.search(text))
        has_verb = bool(_ANNOUNCE_VERB_RE.search(text))
        is_opinion = bool(_OPINION_RE.search(text))
        if has_money_or_facility and has_verb and not is_opinion:
            results.append({
                "quote": n.get("headline"), "source_kind": "뉴스",
                "url": n.get("url"), "date": news_date_str(n),
            })
        if len(results) >= max_items:
            break
    return results


@st.cache_data(ttl=3600, show_spinner=False)
def find_commentary(ticker, company_name, metric_key, period_end_date, max_quotes=3):
    """1순위 8-K, 없으면 2순위 뉴스(현재 capex만 지원)로 폴백. 둘 다 없으면 빈 리스트 —
    "N개 이유"를 강제하지 않고 실제로 찾은 만큼만 반환한다."""
    quotes = find_earnings_commentary(ticker, metric_key, period_end_date, max_quotes)
    if quotes:
        return quotes
    if metric_key == "capex":
        return find_capex_news(ticker, company_name, max_items=max_quotes)
    return []
