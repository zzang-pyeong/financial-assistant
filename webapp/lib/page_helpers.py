from datetime import datetime

import streamlit as st


def inject_base_styles():
    """앱 전체 글꼴을 각진 느낌의 산세리프(IBM Plex Sans KR)로 통일하고,
    기본 스피너 아이콘을 데이터 수집 컨셉에 맞는 회전 이모지로 교체."""
    st.markdown(
        "<style>"
        "@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600;700&display=swap');"
        "html, body, .stApp, .stApp * { font-family: 'IBM Plex Sans KR', sans-serif !important; }"
        "[data-testid='stIconMaterial'], [data-testid='stIconMaterial'] * {"
        "  font-family: 'Material Symbols Rounded' !important;"
        "}"
        "@keyframes spin-emoji { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }"
        "[data-testid='stSpinnerIcon'] {"
        "  background: none !important; border: none !important;"
        "  width: 1.3em !important; height: 1.3em !important;"
        "  display: inline-flex !important; align-items: center; justify-content: center;"
        "}"
        "[data-testid='stSpinnerIcon']::before {"
        "  content: '\\1F310'; display: inline-block; font-size: 1.15rem;"
        "  animation: spin-emoji 1.1s linear infinite;"
        "}"
        "div.st-key-page_header { text-align: center; }"
        "div.st-key-page_header [data-testid='stCaptionContainer'] { justify-content: center; }"
        "div.st-key-page_header [data-testid='stPageLink'] { justify-content: center; }"
        "</style>",
        unsafe_allow_html=True,
    )


def render_wordmark(first, second, size="2.2rem", align="left", margin="0 0 1rem 0", sep=" "):
    """EnterTicker/Conflict Point와 같은 타이포그래피 스타일의 2단어 워드마크.
    두 번째 단어만 브랜드 블루로 강조. sep="" 이면 EnterTicker처럼 붙여 쓴다."""
    st.markdown(
        f"<div style='text-align:{align}; margin:{margin}; font-size:{size}; "
        f"font-weight:700; letter-spacing:-0.02em;'>"
        f"{first}{sep}<span style='color:#2f6fed;'>{second}</span></div>",
        unsafe_allow_html=True,
    )


def require_analysis():
    """상세 데이터 하위 페이지: 아직 조회 전이면 메인 페이지로 안내하고 중단."""
    if "peer_data" not in st.session_state:
        st.info("Search a ticker on the main page first.")
        st.page_link("app.py", label="← Back to Search", icon="🏠")
        st.stop()


def news_date_str(n):
    """Finnhub unix timestamp를 날짜로 변환 — 뉴스 신선도 표시용."""
    ts = n.get("datetime")
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    except (ValueError, OSError):
        return None
