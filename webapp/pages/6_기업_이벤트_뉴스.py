import sys
from pathlib import Path

import streamlit as st

sys.path.append(str(Path(__file__).parent.parent))

from lib._shared_core.translate import to_korean, prefetch_korean
from lib._shared_core.config import ANALYST_NEWS_LOOKBACK_DAYS, CORPORATE_EVENT_DISPLAY_LIMIT
from lib._shared_core.page_helpers import (
    require_analysis, news_date_str, inject_base_styles, render_wordmark, render_ticker_header,
)
from lib._shared_core.search import render_sidebar

st.set_page_config(page_title="Company Events — EnterTicker", layout="wide")
inject_base_styles()
require_analysis()

with st.sidebar:
    render_sidebar()

ticker = st.session_state.ticker
with st.container(key="page_header"):
    render_wordmark("Company", "Events", align="center")
    render_ticker_header(ticker)
    st.caption("M&A · 경영진 교체 · 신규 계약/파트너십")
st.divider()

st.caption(
    f"최근 {ANALYST_NEWS_LOOKBACK_DAYS}일 뉴스 중 인수합병·경영진 교체·신규 계약 관련 키워드가 "
    "있는 것만 근사 필터링한 것입니다. ⚠️ 키워드 매칭 기반 근사치이며, 정밀 이벤트 추출이 아닙니다."
)
corporate_events = st.session_state.get("corporate_events", [])
if corporate_events:
    shown = corporate_events[:CORPORATE_EVENT_DISPLAY_LIMIT]
    # 표시할 헤드라인을 먼저 한꺼번에 병렬 번역 (Analyst News 페이지와 같은 이유)
    with st.spinner("헤드라인 번역 중..."):
        prefetch_korean([ev["headline"] for ev in shown])
    for ev in shown:
        cats = ", ".join(f"{c['category']}({', '.join(c['matched'])})" for c in ev["categories"])
        headline = to_korean(ev["headline"])
        title = f"[{headline}]({ev['url']})" if ev.get("url") else headline
        date_str = news_date_str(ev)
        date_part = f" ({date_str})" if date_str else ""
        st.write(f"- {title}{date_part}")
        st.caption(f"분류: {cats} · _({ev['source']})_")
else:
    st.caption("해당 기간 내 M&A·경영진 교체·신규 계약 관련 뉴스 없음")
