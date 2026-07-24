import sys
from pathlib import Path
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

sys.path.append(str(Path(__file__).parent.parent))

from lib.data import get_option_expirations, get_option_chain
from lib.page_helpers import require_analysis, inject_base_styles, render_wordmark
from lib.search import render_sidebar

st.set_page_config(page_title="Options Data — EnterTicker", layout="wide")
inject_base_styles()
require_analysis()

with st.sidebar:
    render_sidebar()

ticker = st.session_state.ticker
render_wordmark("Options", "Data")
st.caption(ticker)
st.caption(
    "⚠️ '지금 이 순간'의 스냅샷입니다. 과거 추이가 아니라, 앞으로 6개월 이내 만기가 도래할 "
    "옵션들의 현재 미결제약정(OI)·거래량을 보여줍니다."
)
st.page_link("app.py", label="← Back to Search", icon="🏠")
st.divider()

expirations = get_option_expirations(ticker)
if not expirations:
    st.info("이 종목은 옵션 데이터를 제공하지 않거나 조회에 실패했습니다.")
    st.stop()

cutoff = date.today() + timedelta(days=185)
near_expirations = [e for e in expirations if datetime.strptime(e, "%Y-%m-%d").date() <= cutoff]

if not near_expirations:
    st.info("앞으로 6개월 이내 만기인 옵션이 없습니다 (가장 가까운 만기가 6개월 이후입니다).")
    st.stop()

st.subheader("만기별 미결제약정(OI) 형성 현황 (향후 6개월)")
rows = []
with st.spinner("만기별 옵션 데이터 조회 중..."):
    for exp in near_expirations:
        calls, puts = get_option_chain(ticker, exp)
        if calls is None or puts is None:
            continue
        rows.append({
            "만기일": exp,
            "콜 OI 합계": int(calls["openInterest"].fillna(0).sum()),
            "풋 OI 합계": int(puts["openInterest"].fillna(0).sum()),
            "콜 거래량 합계": int(calls["volume"].fillna(0).sum()),
            "풋 거래량 합계": int(puts["volume"].fillna(0).sum()),
        })

if not rows:
    st.info("옵션 체인 데이터를 가져오지 못했습니다.")
    st.stop()

summary_df = pd.DataFrame(rows)
summary_df["풋/콜 OI 비율"] = (
    summary_df["풋 OI 합계"] / summary_df["콜 OI 합계"].replace(0, pd.NA)
).round(2)
st.dataframe(summary_df, use_container_width=True, hide_index=True)

with st.expander("📖 이 표, 어떻게 해석하나요?", expanded=True):
    st.markdown(
        "- **OI(미결제약정)**: 아직 청산되지 않고 남아있는 계약 수. 클수록 그 만기·방향에 시장의 "
        "관심/포지션이 많이 몰려 있다는 뜻입니다.\n"
        "- **풋/콜 OI 비율**: 콜 대비 풋이 얼마나 쌓여 있는지. 1보다 크면 풋이 더 많다는 뜻입니다.\n"
        "- **예시**: 어떤 만기의 풋/콜 비율이 유독 2.0으로 다른 만기(보통 0.5~1.0)보다 튀어 있다면, "
        "그 시점(예: 실적 발표 직후 만기)에 하락 리스크를 헤지하려는 수요가 몰렸을 가능성을 "
        "의심해볼 수 있습니다.\n"
        "- **주의**: 풋 매수만 있는 게 아니라 풋 매도(하락 안 할 거라는 베팅)도 이 숫자에 섞여 "
        "있어서, 비율 하나만으로 '시장이 하락을 예상한다'고 단정할 수 없습니다 — 어디까지나 "
        "참고용 신호입니다."
    )

st.divider()
st.subheader("만기 선택 → 행사가별 상세")
chosen = st.selectbox("만기일 선택", near_expirations)
calls, puts = get_option_chain(ticker, chosen)
if calls is not None and puts is not None:
    col1, col2 = st.columns(2)
    with col1:
        st.write("**콜(Call)**")
        st.dataframe(
            calls[["strike", "openInterest", "volume", "impliedVolatility"]].sort_values("strike"),
            use_container_width=True, hide_index=True,
        )
    with col2:
        st.write("**풋(Put)**")
        st.dataframe(
            puts[["strike", "openInterest", "volume", "impliedVolatility"]].sort_values("strike"),
            use_container_width=True, hide_index=True,
        )
    with st.expander("📖 이 표, 어떻게 해석하나요?"):
        st.markdown(
            "- **행사가(strike)별로 OI·거래량이 튀는 지점**은 시장 참여자들이 '이 가격대가 중요하다'고 "
            "보고 있다는 뜻입니다 — 특히 현재가와 가까운 행사가에 몰려 있으면 단기 지지/저항선처럼 "
            "참고할 수 있습니다.\n"
            "- **예시**: 현재가가 $200인데 $210 콜에 OI가 유독 많이 쌓여 있다면, 그 가격대를 "
            "저항선(넘기 어려운 매물대)처럼 보는 참여자가 많다는 신호로 흔히 해석됩니다.\n"
            "- **IV(implied volatility, 내재변동성)**: 시장이 앞으로 가격이 얼마나 크게 흔들릴 것으로 "
            "보는지를 나타내는 값. 평소보다 유독 높은 행사가/만기가 있다면 그 근처에 불확실성(실적, "
            "소송 결과 등)이 몰려 있다는 뜻일 수 있습니다.\n"
            "- **주의**: 이 역시 매수/매도 신호가 아니라 '시장이 어디를 주목하는지'를 보여주는 "
            "참고 자료입니다."
        )
else:
    st.info("해당 만기의 옵션 데이터를 가져오지 못했습니다.")
