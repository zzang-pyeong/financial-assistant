import os
import re
import requests
import streamlit as st
import FinanceDataReader as fdr
import yfinance as yf
from dotenv import load_dotenv

from .translate import to_english

load_dotenv()

_KOREAN_RE = re.compile(r"[가-힣]")
_TICKER_RE = re.compile(r"^[A-Z]{1,5}(\.[A-Z]{1,3})?$")
_US_EXCHANGES = {"NMS", "NYQ", "NGM", "NCM", "ASE", "PCX", "BATS", "PNK"}


def _get_secret(key, default=""):
    """로컬 개발: .env 파일. Streamlit Cloud 배포: 대시보드 Secrets.
    두 환경 모두 같은 코드로 동작하도록 st.secrets를 우선 확인하고, 없으면 환경변수로 폴백."""
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.environ.get(key, default)


FINNHUB_KEY = _get_secret("FINNHUB_API_KEY")


@st.cache_data(ttl=3600, show_spinner=False)
def get_price_history(ticker, start="2024-01-01"):
    return fdr.DataReader(ticker, start)


@st.cache_data(ttl=300, show_spinner=False)
def get_intraday_price_history(ticker, interval, period):
    """분봉 데이터 — Yahoo Finance 제약상 interval별로 조회 가능한 최대 period가 다름
    (1m: 최근 7일, 5m/15m/30m: 최근 60일, 60m: 최근 2년 등). 5분 캐시로 너무 잦은
    재호출은 막되, 장중 갱신을 위해 일봉보다 짧게 잡음.

    yfinance는 인덱스를 거래소 현지시간(미국 동부, America/New_York)으로 반환한다.
    사용자는 한국에서 보므로 화면에 보이는 시각과 실제 미국 장중 시각이 어긋나
    보이지 않도록 한국시간(KST)으로 변환해서 반환한다."""
    try:
        df = yf.Ticker(ticker).history(period=period, interval=interval)
        if df is None or df.empty:
            return None
        if df.index.tz is not None:
            df = df.copy()
            df.index = df.index.tz_convert("Asia/Seoul")
        return df
    except Exception:
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def get_yf_info(ticker):
    try:
        return yf.Ticker(ticker).info
    except Exception:
        return {}


@st.cache_data(ttl=3600, show_spinner=False)
def get_yf_calendar(ticker):
    try:
        cal = yf.Ticker(ticker).calendar
        if cal and "Earnings Date" in cal and cal["Earnings Date"]:
            return cal["Earnings Date"][0]
        return None
    except Exception:
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def get_mutualfund_holders(ticker):
    try:
        df = yf.Ticker(ticker).mutualfund_holders
        return df
    except Exception:
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def get_insider_transactions(ticker):
    try:
        df = yf.Ticker(ticker).insider_transactions
        return df
    except Exception:
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def get_business_summary(ticker):
    info = get_yf_info(ticker)
    return (info.get("longBusinessSummary") or "").lower()


@st.cache_data(ttl=3600, show_spinner=False)
def get_finnhub_peers(ticker):
    if not FINNHUB_KEY:
        return []
    try:
        r = requests.get(
            "https://finnhub.io/api/v1/stock/peers",
            params={"symbol": ticker, "token": FINNHUB_KEY},
            timeout=10,
        )
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception:
        return []


# 로고 URL 캐시 — 관계도가 이 조회를 ThreadPoolExecutor로 병렬 처리하기 때문에
# @st.cache_data를 쓸 수 없다(워커 스레드에서 호출하면 ScriptRunContext 경고가 난다).
# lib/translate.py, lib/sec_filings.py와 같은 이유·같은 패턴.
_LOGO_CACHE = {}
_LOGO_CACHE_MAX = 2000


def _fetch_company_logo_url(ticker):
    """Finnhub company-profile2에서 로고 URL만 뽑아온다. 캐시도 Streamlit 의존도 없어
    워커 스레드에서 호출해도 안전하다. 실패·빈 응답·로고 없음은 전부 None."""
    if not FINNHUB_KEY:
        return None
    try:
        r = requests.get(
            "https://finnhub.io/api/v1/stock/profile2",
            params={"symbol": ticker, "token": FINNHUB_KEY},
            timeout=10,
        )
        data = r.json()
        return (data.get("logo") or None) if isinstance(data, dict) else None
    except Exception:
        return None


def get_company_logo_url(ticker):
    """회사 로고 이미지 URL 또는 None. 로고는 거의 안 바뀌므로 프로세스 수명 동안 캐시한다.

    ⚠️ None이 흔한 정상 경로다 — Finnhub가 로고를 못 주는 회사가 특히 소형주에 많다.
    호출부는 로고가 없는 노드를 정상적으로 그릴 수 있어야 한다(관계도는 빈 원으로 폴백)."""
    if not ticker:
        return None
    key = ticker.upper()
    if key in _LOGO_CACHE:
        return _LOGO_CACHE[key]
    url = _fetch_company_logo_url(ticker)
    if len(_LOGO_CACHE) >= _LOGO_CACHE_MAX:
        for k in list(_LOGO_CACHE)[: _LOGO_CACHE_MAX // 5]:
            _LOGO_CACHE.pop(k, None)
    _LOGO_CACHE[key] = url
    return url


@st.cache_data(ttl=3600, show_spinner=False)
def get_finnhub_recommendation_trends(ticker):
    if not FINNHUB_KEY:
        return []
    try:
        r = requests.get(
            "https://finnhub.io/api/v1/stock/recommendation",
            params={"symbol": ticker, "token": FINNHUB_KEY},
            timeout=10,
        )
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception:
        return []


@st.cache_data(ttl=3600, show_spinner=False)
def get_finnhub_price_target(ticker):
    """평균/최고/최저/중앙값 목표주가 — Finnhub 프리미엄 플랜 전용 엔드포인트라 무료
    키에서는 빈 dict가 흔하다(호출부 lib/qualitative.py::summarize_price_target이
    get_yf_analyst_price_targets()로 폴백)."""
    if not FINNHUB_KEY:
        return {}
    try:
        r = requests.get(
            "https://finnhub.io/api/v1/stock/price-target",
            params={"symbol": ticker, "token": FINNHUB_KEY},
            timeout=10,
        )
        data = r.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


@st.cache_data(ttl=3600, show_spinner=False)
def get_finnhub_upgrade_downgrade(ticker):
    """최근 애널리스트 상향/하향 이력 — 마찬가지로 Finnhub 프리미엄 전용이라 무료
    키에서는 빈 리스트가 흔하다(get_yf_upgrades_downgrades()로 폴백)."""
    if not FINNHUB_KEY:
        return []
    try:
        r = requests.get(
            "https://finnhub.io/api/v1/stock/upgrade-downgrade",
            params={"symbol": ticker, "token": FINNHUB_KEY},
            timeout=10,
        )
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception:
        return []


@st.cache_data(ttl=3600, show_spinner=False)
def get_yf_analyst_price_targets(ticker):
    """Finnhub 목표주가가 비었을 때(무료 키 제약) 쓰는 폴백 — yfinance는 무료로 제공."""
    try:
        data = yf.Ticker(ticker).analyst_price_targets
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


@st.cache_data(ttl=3600, show_spinner=False)
def get_yf_upgrades_downgrades(ticker):
    """Finnhub 상향/하향 이력이 비었을 때 쓰는 폴백. 날짜는 앱 전역 관례대로 unix epoch로
    맞춰서 반환한다(다른 뉴스/공시 근거와 같은 방식으로 다뤄지도록)."""
    try:
        df = yf.Ticker(ticker).upgrades_downgrades
        if df is None or df.empty:
            return []
        rows = []
        for grade_date, row in df.iterrows():
            try:
                epoch = int(grade_date.timestamp())
            except Exception:
                epoch = None
            pt = row.get("currentPriceTarget")
            prior_pt = row.get("priorPriceTarget")
            rows.append({
                "date": epoch, "firm": row.get("Firm"),
                "from_grade": row.get("FromGrade"), "to_grade": row.get("ToGrade"),
                "action": row.get("Action"),
                # NaN != NaN — pandas가 값 없을 때 NaN을 주므로 이 트릭으로 걸러낸다.
                "price_target": float(pt) if isinstance(pt, (int, float)) and pt == pt else None,
                # 신규 커버리지 개시(초기 등급 부여) 건은 이전 목표주가가 없어 yfinance가
                # 0.0을 준다 — 진짜 $0 목표주가는 없으므로 0도 "없음"으로 취급.
                "prior_price_target": (
                    float(prior_pt) if isinstance(prior_pt, (int, float))
                    and prior_pt == prior_pt and prior_pt > 0 else None
                ),
            })
        return rows
    except Exception:
        return []


@st.cache_data(ttl=1800, show_spinner=False)
def get_finnhub_company_news(ticker, from_date, to_date):
    if not FINNHUB_KEY:
        return []
    try:
        r = requests.get(
            "https://finnhub.io/api/v1/company-news",
            params={"symbol": ticker, "from": from_date, "to": to_date, "token": FINNHUB_KEY},
            timeout=10,
        )
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception:
        return []


@st.cache_data(ttl=1800, show_spinner=False)
def get_option_expirations(ticker):
    """만기일 목록 (YYYY-MM-DD 문자열). yfinance는 '현재 시점' 옵션 체인만 제공 —
    과거 추이가 아니라 앞으로 도래할 만기들의 지금 상태만 볼 수 있음."""
    try:
        return list(yf.Ticker(ticker).options)
    except Exception:
        return []


@st.cache_data(ttl=1800, show_spinner=False)
def get_option_chain(ticker, expiration):
    """특정 만기일의 콜/풋 옵션 체인 (행사가별 미결제약정·거래량·IV)."""
    try:
        oc = yf.Ticker(ticker).option_chain(expiration)
        return oc.calls, oc.puts
    except Exception:
        return None, None


@st.cache_data(ttl=3600, show_spinner=False)
def yahoo_symbol_search(query):
    """Yahoo Finance 검색 API — 회사명으로 티커를 찾을 때 씀. 한글 쿼리는 지원 안 함(400 에러
    실증 확인) — 호출 전에 영문으로 번역해서 넣어야 함."""
    try:
        r = requests.get(
            "https://query2.finance.yahoo.com/v1/finance/search",
            params={"q": query, "quotesCount": 5, "newsCount": 0},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        data = r.json()
        return data.get("quotes", [])
    except Exception:
        return []


def resolve_ticker(raw_query):
    """사용자가 티커를 직접 입력하면 그대로, 한글/영문 기업명을 입력하면 검색해서
    실제 티커로 변환한다. 반환: (ticker, matched_name) — matched_name은 검색으로
    찾았을 때만 채워지고, 티커를 그대로 쓴 경우 None."""
    query = (raw_query or "").strip()
    if not query:
        return "", None

    if _TICKER_RE.match(query):
        return query, None  # 이미 순수 대문자 티커 형태 — 검색 없이 그대로 사용

    search_term = to_english(query) if _KOREAN_RE.search(query) else query
    quotes = yahoo_symbol_search(search_term)
    equities = [q for q in quotes if q.get("quoteType") == "EQUITY"]
    us_equities = [q for q in equities if q.get("exchange") in _US_EXCHANGES]
    candidates = us_equities or equities

    if candidates:
        top = candidates[0]
        return top["symbol"], (top.get("longname") or top.get("shortname"))

    # 검색 실패 시 마지막 수단으로 원본을 티커 형태로 시도
    return query.upper(), None
