import sys
from pathlib import Path

import streamlit as st

sys.path.append(str(Path(__file__).parent.parent))

from lib.translate import to_korean
from lib.config import ANALYST_NEWS_LOOKBACK_DAYS
from lib.page_helpers import require_analysis, news_date_str, inject_base_styles, render_wordmark
from lib.search import render_sidebar

st.set_page_config(page_title="Analyst News — EnterTicker", layout="wide")
inject_base_styles()
require_analysis()

with st.sidebar:
    render_sidebar()

ticker = st.session_state.ticker
with st.container(key="page_header"):
    render_wordmark("Analyst", "News", align="center")
    st.caption(ticker)
st.divider()

st.caption(
    f"최근 {ANALYST_NEWS_LOOKBACK_DAYS}일 뉴스 중 'upgrade/price target' 등 키워드가 있는 것만 필터링. "
    "⚠️ 실제 매수/매도 집계의 확정된 근거는 아니며, 관련 있어 보이는 뉴스일 뿐입니다."
)
analyst_news = st.session_state.get("analyst_news", [])
if analyst_news:
    for n in analyst_news[:8]:
        headline = to_korean(n["headline"])
        title = f"[{headline}]({n['url']})" if n.get("url") else headline
        date_str = news_date_str(n)
        date_part = f" ({date_str})" if date_str else ""
        st.write(f"- {title}{date_part}")
        st.caption(f"매칭 키워드: {', '.join(n['matched'])} _({n.get('source', '')})_")
else:
    st.caption("해당 기간 내 애널리스트 관련 뉴스 없음")
