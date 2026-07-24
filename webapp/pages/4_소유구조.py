import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.append(str(Path(__file__).parent.parent))

from lib.ownership import insider_trade_direction, float_ratio_interpretation, institution_pct_interpretation
from lib.glossary import render_glossary
from lib.page_helpers import require_analysis, inject_base_styles, render_wordmark
from lib.search import render_sidebar

st.set_page_config(page_title="Ownership Map — EnterTicker", layout="wide")
inject_base_styles()
require_analysis()

with st.sidebar:
    render_sidebar()

ticker = st.session_state.ticker
render_wordmark("Ownership", "Map")
st.caption(ticker)
st.page_link("app.py", label="← Back to Search", icon="🏠")
st.divider()

own = st.session_state.ownership
fund_ap_preview = st.session_state.fund_ap
insider_tx_preview = st.session_state.insider_tx
direction_preview = insider_trade_direction(insider_tx_preview)

summary_rows = []
if own["institutions_pct"] is not None:
    summary_rows.append({
        "지표": "기관 보유율", "값": f"{own['institutions_pct']*100:.1f}%",
        "의미": institution_pct_interpretation(own["institutions_pct"]),
    })
if own["insiders_pct"] is not None:
    summary_rows.append({
        "지표": "내부자 보유율", "값": f"{own['insiders_pct']*100:.1f}%",
        "의미": "임원 등 내부자가 직접 보유한 비율 — 높을수록 경영진 이해관계가 주가와 일치",
    })
if own["short_pct_float"] is not None:
    summary_rows.append({
        "지표": "공매도 비율", "값": f"{own['short_pct_float']*100:.1f}%",
        "의미": "높을수록 하락 베팅 비중이 크다는 뜻이지만, 반대로 숏스퀴즈(급반등) 가능성도 있음",
    })
if own["float_ratio"] is not None:
    summary_rows.append({
        "지표": "유동주식비율", "값": f"{own['float_ratio']*100:.1f}%",
        "의미": float_ratio_interpretation(own["float_ratio"]),
    })
if fund_ap_preview:
    total = fund_ap_preview["passive_pct"] + fund_ap_preview["active_pct"]
    if total > 0:
        summary_rows.append({
            "지표": "펀드 Passive:Active",
            "값": f"{fund_ap_preview['passive_pct']/total*100:.0f}% : {fund_ap_preview['active_pct']/total*100:.0f}%",
            "의미": "패시브 비중이 높을수록 지수 편입/이탈에 따른 기계적 매매가 많고, 펀더멘털과 무관한 수급 영향이 큼",
        })
if direction_preview:
    summary_rows.append({
        "지표": "내부자 매매 방향성", "값": direction_preview["direction"],
        "의미": "단순 보유율(%)보다 최근 실제 매수/매도 방향이 더 중요한 신호일 때가 많음",
    })

if summary_rows:
    with st.expander("📋 소유구조 종합 요약표", expanded=True):
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)
        st.caption("⚠️ 각 지표를 병치한 표일 뿐, 하나의 점수로 합산한 것이 아닙니다.")
    st.divider()

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
