import sys
from pathlib import Path

import streamlit as st

sys.path.append(str(Path(__file__).parent.parent))

from lib.translate import to_korean
from lib.config import ANALYST_NEWS_LOOKBACK_DAYS
from lib.page_helpers import require_analysis

st.set_page_config(page_title="애널리스트 관련 뉴스 — Devil's Advocate", layout="wide")
require_analysis()

ticker = st.session_state.ticker
st.title(f"📰 {ticker} — 애널리스트 관련 뉴스 (근사치)")
st.caption("병치만 하고 점수화하지 않습니다 (원칙 B) — 의사결정 흐름과 분리된 참고용 큰 화면 뷰입니다.")
st.page_link("app.py", label="← 메인 흐름으로 돌아가기", icon="🏠")
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
        st.write(f"- {title}")
        st.caption(f"매칭 키워드: {', '.join(n['matched'])} _({n.get('source', '')})_")
else:
    st.caption("해당 기간 내 애널리스트 관련 뉴스 없음")
