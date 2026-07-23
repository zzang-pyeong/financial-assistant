import sys
from pathlib import Path

import streamlit as st

sys.path.append(str(Path(__file__).parent.parent))

from lib.ownership import insider_trade_direction, float_ratio_interpretation, institution_pct_interpretation
from lib.glossary import render_glossary
from lib.page_helpers import require_analysis

st.set_page_config(page_title="소유구조 — Devil's Advocate", layout="wide")
require_analysis()

ticker = st.session_state.ticker
st.title(f"🏛️ {ticker} — 소유구조")
st.caption("병치만 하고 점수화하지 않습니다 (원칙 B) — 의사결정 흐름과 분리된 참고용 큰 화면 뷰입니다.")
st.page_link("app.py", label="← 메인 흐름으로 돌아가기", icon="🏠")
st.divider()

own = st.session_state.ownership
if own["institutions_pct"] is not None:
    st.write(f"기관 보유율: **{own['institutions_pct']*100:.1f}%**")
    st.caption(institution_pct_interpretation(own["institutions_pct"]))
if own["insiders_pct"] is not None:
    st.write(f"내부자 보유율: **{own['insiders_pct']*100:.1f}%**")
if own["short_pct_float"] is not None:
    st.write(f"공매도 비율: **{own['short_pct_float']*100:.1f}%**")
if own["float_ratio"] is not None:
    st.write(f"유동주식비율: **{own['float_ratio']*100:.1f}%**")
    st.caption(float_ratio_interpretation(own["float_ratio"]))

fund_ap = st.session_state.fund_ap
if fund_ap:
    total = fund_ap["passive_pct"] + fund_ap["active_pct"]
    if total > 0:
        st.write(f"펀드 단위 Passive:Active = **{fund_ap['passive_pct']/total*100:.0f}% : {fund_ap['active_pct']/total*100:.0f}%**")
        st.caption("(펀드명 키워드 매칭 기준, 참고용)")

insider_tx = st.session_state.insider_tx
direction = insider_trade_direction(insider_tx)
if direction:
    st.write(f"내부자 매매 방향성: **{direction['direction']}**")
    st.caption(
        f"매수 {direction['buy_count']}건({direction['buy_shares']:,}주) vs "
        f"매도 {direction['sell_count']}건({direction['sell_shares']:,}주) "
        f"— 옵션행사 등 {direction['other_count']}건은 제외"
    )
if insider_tx is not None and not insider_tx.empty:
    with st.expander("최근 내부자 거래 원본 (주식보상 제외)"):
        st.caption("⚠️ IPO 당일 배정분은 자발적 매매가 아닐 수 있음 — 날짜·가격을 직접 확인하세요")
        st.dataframe(insider_tx.head(10), use_container_width=True)

render_glossary(
    ["기관·내부자 보유율", "유동주식비율", "공매도 비율", "내부자 매매 방향성"],
    title="ℹ️ 소유구조 지표 설명",
)
