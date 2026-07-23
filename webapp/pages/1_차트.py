import sys
from pathlib import Path

import streamlit as st

sys.path.append(str(Path(__file__).parent.parent))

from lib.charts import render_price_chart_figure, PERIOD_OPTIONS
from lib.page_helpers import require_analysis

st.set_page_config(page_title="차트 — Devil's Advocate", layout="wide")
require_analysis()

ticker = st.session_state.ticker
st.title(f"📈 {ticker} — 최근 주가 차트")
st.caption("가격·이동평균·거래량만 병치해서 보여줍니다 — 매수/매도 신호를 표시하지 않습니다 (원칙 B).")
st.page_link("app.py", label="← 메인 흐름으로 돌아가기", icon="🏠")
st.divider()

period_label = st.radio(
    "기간", list(PERIOD_OPTIONS.keys()), index=2, horizontal=True, key="chart_period",
)
fig = render_price_chart_figure(st.session_state.df, PERIOD_OPTIONS[period_label])
st.plotly_chart(fig, use_container_width=True)
