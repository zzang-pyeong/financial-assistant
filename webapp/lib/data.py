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
def get_institutional_holders(ticker):
    try:
        df = yf.Ticker(ticker).institutional_holders
        return df
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
