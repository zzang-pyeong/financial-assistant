import sys
from pathlib import Path

import streamlit as st

sys.path.append(str(Path(__file__).parent.parent))

from lib.data import get_intraday_price_history
from lib.charts import render_price_chart_figure, PERIOD_OPTIONS, INTRADAY_OPTIONS, PLOTLY_CONFIG
from lib.page_helpers import require_analysis

st.set_page_config(page_title="차트 — Devil's Advocate", layout="wide")
require_analysis()

ticker = st.session_state.ticker
st.title(f"📈 {ticker} — 최근 주가 차트")
st.page_link("app.py", label="← 메인 흐름으로 돌아가기", icon="🏠")
st.divider()

list_col, chart_col = st.columns([1, 5])

with list_col:
    st.markdown("**일봉**")
    daily_choice = st.radio(
        "일봉 기간", list(PERIOD_OPTIONS.keys()), index=2, key="chart_daily_choice", label_visibility="collapsed",
    )
    st.markdown("**분봉**")
    st.caption("Yahoo 제약상 분봉은 최근 며칠~몇 개월치만 조회됩니다.")
    intraday_choice = st.radio(
        "분봉 단위", list(INTRADAY_OPTIONS.keys()), index=None, key="chart_intraday_choice",
        label_visibility="collapsed",
    )
    st.caption("마우스 드래그로 좌우 이동, 스크롤로 확대/축소할 수 있습니다.")

with chart_col:
    if intraday_choice:
        # 분봉 선택 시 일봉 선택을 무시 — 같은 화면에서 동시에 두 개를 그리지 않음
        interval, period = INTRADAY_OPTIONS[intraday_choice]
        with st.spinner(f"{ticker} {intraday_choice}봉 데이터 조회 중..."):
            intraday_df = get_intraday_price_history(ticker, interval, period)
        if intraday_df is None or intraday_df.empty:
            st.error(f"{intraday_choice}봉 데이터를 가져오지 못했습니다 (Yahoo 제공 범위를 벗어났을 수 있습니다).")
        else:
            st.caption("🕐 시간은 한국시간(KST) 기준입니다 (미국 정규장은 한국시간 밤 22:30~05:00 무렵).")
            st.caption(f"MA20/MA60은 {intraday_choice} 봉 기준 20개/60개 이동평균입니다 (일봉 MA와 단위가 다릅니다).")
            fig = render_price_chart_figure(intraday_df, period_days=None)
            st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)
    else:
        fig = render_price_chart_figure(st.session_state.df, PERIOD_OPTIONS[daily_choice])
        st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)
