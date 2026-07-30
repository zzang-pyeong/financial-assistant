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
from lib._shared_page2_page8_filings.sec_filings import find_capital_raise_filings

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
        headline = to_korean(ev["headline"]).replace("$", "\\$")
        title = f"[{headline}]({ev['url']})" if ev.get("url") else headline
        date_str = news_date_str(ev)
        date_part = f" ({date_str})" if date_str else ""
        st.write(f"- {title}{date_part}")
        st.caption(f"분류: {cats} · _({ev['source']})_")
else:
    st.caption("해당 기간 내 M&A·경영진 교체·신규 계약 관련 뉴스 없음")

st.divider()
st.markdown("#### 유상증자·자본조달 공시")
st.caption(
    "최근 1년 내 S-1·S-3·424B(신주·회사채 등록/공모) SEC 공시 목록입니다. 뉴스 키워드가 "
    "아니라 공시 폼타입 자체를 근거로 하며, 공시가 있었다는 사실만 보여줍니다 — 실제 발행 "
    "여부·규모·조건은 원문(링크)에서 확인하세요."
)
if st.session_state.get("capital_raise_filings_ticker") != ticker:
    with st.spinner("SEC 등록/공모 공시(S-1·S-3·424B) 확인 중..."):
        capital_raise_filings = find_capital_raise_filings(ticker)
    st.session_state.update(
        capital_raise_filings=capital_raise_filings, capital_raise_filings_ticker=ticker,
    )
capital_raise_filings = st.session_state.get("capital_raise_filings", [])
if capital_raise_filings:
    for ev in capital_raise_filings:
        headline = ev["headline"].replace("$", "\\$")
        title = f"[{headline}]({ev['url']})" if ev.get("url") else headline
        date_str = news_date_str(ev)
        date_part = f" ({date_str})" if date_str else ""
        st.write(f"- {title}{date_part}")
        st.caption(f"_({ev['source']})_")
else:
    st.caption("해당 기간 내 S-1·S-3·424B 공시 없음")
