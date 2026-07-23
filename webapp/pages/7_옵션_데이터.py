import sys
from pathlib import Path
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

sys.path.append(str(Path(__file__).parent.parent))

from lib.data import get_option_expirations, get_option_chain
from lib.page_helpers import require_analysis

st.set_page_config(page_title="옵션 데이터 — Devil's Advocate", layout="wide")
require_analysis()

ticker = st.session_state.ticker
st.title(f"🧮 {ticker} — 옵션 데이터")
st.caption("병치만 하고 점수화하지 않습니다 (원칙 B) — 매수/매도 신호를 표시하지 않습니다.")
st.caption(
    "⚠️ '지금 이 순간'의 스냅샷입니다. 과거 추이가 아니라, 앞으로 6개월 이내 만기가 도래할 "
    "옵션들의 현재 미결제약정(OI)·거래량을 보여줍니다."
)
st.page_link("app.py", label="← 메인 흐름으로 돌아가기", icon="🏠")
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
st.caption(
    "⚠️ 풋/콜 비율이 높을수록 흔히 '하락 베팅 우위'로 해석되지만, 헤지 목적의 풋 매수도 섞여 "
    "있어 방향성을 확정하는 근거는 아닙니다."
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
else:
    st.info("해당 만기의 옵션 데이터를 가져오지 못했습니다.")
