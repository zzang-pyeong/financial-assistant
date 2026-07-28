from datetime import datetime

import streamlit as st

from .data import get_company_logo_url


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


def render_ticker_header(ticker, suffix=None):
    """페이지 헤더의 티커 표시 — 굵고 진한 글씨 + 정사각형 회사 로고를 나란히 보여준다
    (사용자 피드백: 기존 st.caption(ticker)은 옅은 회색이라 눈에 잘 안 띔). suffix가
    있으면 " · {suffix}"를 이어붙인다(예: 관계도의 "기업 연결 근거").
    로고는 object-fit:contain으로 정사각 틀에 맞춰서 넣는다 — 관계도 그래프 노드의 원형
    크롭(lib/logos.py)과 달리 여기는 일반 HTML이라 서버 가공 없이 CSS만으로 충분하다.
    로고가 없는 종목(소형주 등)은 텍스트만 — 로고 없음은 흔한 정상 경로."""
    logo_url = get_company_logo_url(ticker)
    logo_html = (
        f"<img src='{logo_url}' style='width:28px; height:28px; object-fit:contain; "
        "border-radius:6px; border:1px solid #e5e7eb; padding:2px; background:#fff;' />"
        if logo_url else ""
    )
    suffix_html = (
        f"<span style='color:#6b7280; font-weight:400;'> · {suffix}</span>" if suffix else ""
    )
    st.markdown(
        "<div style='display:flex; align-items:center; justify-content:center; "
        f"gap:0.45rem; font-size:1.05rem;'>{logo_html}"
        f"<span style='font-weight:700; color:#111827;'>{ticker}</span>{suffix_html}</div>",
        unsafe_allow_html=True,
    )


def render_info_cards(cards):
    """label/value(/sub/delta) 카드 그리드. st.metric은 값이 조금만 길어도 말줄임표로
    잘라버려서(실측: TSLA 시가총액 "$1,193.6...", 날짜 "2026-07-...") 대신 직접 HTML로
    그린다 — flex-wrap이라 좁은 화면에선 자동 줄바꿈되고, 값도 word-break로 감싸 잘리지
    않는다. cards: [(label, value), (label, value, sub), (label, value, sub, delta), ...].
    delta는 이 앱 규칙(색상으로 유불리 암시 안 함)에 맞춰 색 없이 +/- 기호로만 방향 표시."""
    def _card(item):
        label, value = item[0], item[1]
        sub = item[2] if len(item) > 2 else None
        delta = item[3] if len(item) > 3 else None
        sub_html = (
            f"<div style='font-size:0.75rem; color:#9ca3af; margin-top:0.25rem;'>{sub}</div>"
            if sub else ""
        )
        delta_html = (
            f"<div style='font-size:0.85rem; color:#4b5563; margin-top:0.3rem;'>{delta}</div>"
            if delta else ""
        )
        return (
            "<div style='flex:1 1 150px; min-width:150px; padding:0.9rem 1.1rem; "
            "border:1px solid #e5e7eb; border-radius:12px; background:#fafbfc;'>"
            f"<div style='font-size:0.8rem; color:#6b7280; margin-bottom:0.35rem; "
            f"word-break:break-word;'>{label}</div>"
            f"<div style='font-size:1.4rem; font-weight:700; color:#111827; line-height:1.25; "
            f"word-break:break-word;'>{value}</div>{sub_html}{delta_html}</div>"
        )

    html = "".join(_card(c) for c in cards)
    st.markdown(
        f"<div style='display:flex; flex-wrap:wrap; gap:0.9rem; margin:0.6rem 0 1.2rem 0;'>{html}</div>",
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
