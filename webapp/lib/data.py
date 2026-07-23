import os
import requests
import streamlit as st
import FinanceDataReader as fdr
import yfinance as yf
from dotenv import load_dotenv

load_dotenv()


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
