from datetime import datetime

import streamlit as st


def require_analysis():
    """상세 데이터 하위 페이지: 아직 조회 전이면 메인 페이지로 안내하고 중단."""
    if "peer_data" not in st.session_state:
        st.info("먼저 메인 페이지에서 티커를 조회해주세요.")
        st.page_link("app.py", label="← 메인 페이지로", icon="🏠")
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
