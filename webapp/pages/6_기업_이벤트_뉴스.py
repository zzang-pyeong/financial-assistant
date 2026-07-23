import sys
from pathlib import Path

import streamlit as st

sys.path.append(str(Path(__file__).parent.parent))

from lib.translate import to_korean
from lib.config import ANALYST_NEWS_LOOKBACK_DAYS
from lib.page_helpers import require_analysis, news_date_str

st.set_page_config(page_title="기업 이벤트 뉴스 — Devil's Advocate", layout="wide")
require_analysis()

ticker = st.session_state.ticker
st.title(f"🏢 {ticker} — 주요 기업 이벤트 뉴스")
st.caption("M&A · 경영진 교체 · 신규 계약/파트너십")
st.page_link("app.py", label="← 메인 흐름으로 돌아가기", icon="🏠")
st.divider()

st.caption(
    f"최근 {ANALYST_NEWS_LOOKBACK_DAYS}일 뉴스 중 인수합병·경영진 교체·신규 계약 관련 키워드가 "
    "있는 것만 근사 필터링한 것입니다. ⚠️ 키워드 매칭 기반 근사치이며, 정밀 이벤트 추출이 아닙니다."
)
corporate_events = st.session_state.get("corporate_events", [])
if corporate_events:
    for ev in corporate_events[:10]:
        cats = ", ".join(f"{c['category']}({', '.join(c['matched'])})" for c in ev["categories"])
        headline = to_korean(ev["headline"])
        title = f"[{headline}]({ev['url']})" if ev.get("url") else headline
        date_str = news_date_str(ev)
        date_part = f" ({date_str})" if date_str else ""
        st.write(f"- {title}{date_part}")
        st.caption(f"분류: {cats} · _({ev['source']})_")
else:
    st.caption("해당 기간 내 M&A·경영진 교체·신규 계약 관련 뉴스 없음")
