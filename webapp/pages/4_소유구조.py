import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.append(str(Path(__file__).parent.parent))

from lib.ownership import (
    get_fund_level_active_passive, get_recent_insider_transactions,
    insider_trade_direction, float_ratio_interpretation, institution_pct_interpretation,
    insider_pct_interpretation,
)
from lib.glossary import render_glossary
from lib.page_helpers import require_analysis, inject_base_styles, render_wordmark
from lib.search import render_sidebar

st.set_page_config(page_title="Ownership Map — EnterTicker", layout="wide")
inject_base_styles()
require_analysis()

with st.sidebar:
    render_sidebar()

ticker = st.session_state.ticker
with st.container(key="page_header"):
    render_wordmark("Ownership", "Map", align="center")
    st.caption(ticker)
    st.page_link("app.py", label="← Back to Search", icon="🏠")
st.divider()

own = st.session_state.ownership
# 펀드 보유·내부자 거래는 Conflict Board에서 쓰지 않는 비용 큰 요청이므로 이 페이지에서만 로드.
if st.session_state.get("ownership_details_ticker") != ticker:
    with st.spinner("펀드 보유·내부자 거래를 불러오는 중..."):
        fund_ap, insider_tx = get_fund_level_active_passive(ticker), get_recent_insider_transactions(ticker)
    st.session_state.update(
        fund_ap=fund_ap,
        insider_tx=insider_tx,
        ownership_details_ticker=ticker,
    )

fund_ap_preview = st.session_state.get("fund_ap")
insider_tx_preview = st.session_state.get("insider_tx")
direction_preview = insider_trade_direction(insider_tx_preview)

summary_rows = []
interpretation_lines = []

if own["institutions_pct"] is not None:
    summary_rows.append({"지표": "기관 보유율", "값": f"{own['institutions_pct']*100:.1f}%"})
    interpretation_lines.append(("기관 보유율", institution_pct_interpretation(own["institutions_pct"])))
if own["insiders_pct"] is not None:
    summary_rows.append({"지표": "내부자 보유율", "값": f"{own['insiders_pct']*100:.1f}%"})
    interpretation_lines.append(("내부자 보유율", insider_pct_interpretation(own["insiders_pct"])))
if own["institutions_pct"] is not None and own["insiders_pct"] is not None:
    # 기관(13F 공시)·내부자(Form 3/4/5 공시)는 서로 다른 제도라 둘을 더해도 100%가 안 됨 —
    # 실측: NVDA 75.5%, AAPL 68.1%, TSLA 61.5%, USAR 65.5%, AMD 74.5% (전부 미달).
    # 나머지를 "개인 보유율"로 단정하면 안 되므로 그 자체를 지표로 보여줌.
    combined = own["institutions_pct"] + own["insiders_pct"]
    summary_rows.append({"지표": "기관+내부자 합계", "값": f"{combined*100:.1f}%"})
    interpretation_lines.append((
        "기관+내부자 합계",
        f"나머지 {(1 - combined)*100:.1f}%는 '개인 투자자 보유율'이 아니라 두 공시 제도"
        "(기관=13F, 내부자=Form 3·4·5) 어디에도 안 잡히는 나머지입니다 — 소규모 리테일 "
        "투자자, 13F 신고 문턱(운용자산 1억 달러) 미만 소형 기관, 일부 해외 보유분 등이 "
        "섞여 있어 이 차이만으로 개인 보유 비중을 단정할 수 없습니다. (두 수치는 서로 다른 "
        "공시 제도 기반이라 드물게 겹쳐서 100%를 넘는 경우도 있을 수 있습니다.)",
    ))
if own["short_pct_float"] is not None:
    summary_rows.append({"지표": "공매도 비율", "값": f"{own['short_pct_float']*100:.1f}%"})
    interpretation_lines.append((
        "공매도 비율",
        "높을수록 하락 베팅 비중이 크다는 뜻이지만, 반대로 숏스퀴즈(급반등) 가능성도 있음",
    ))
if own["float_ratio"] is not None:
    float_label = "유동주식비율" + (" (추정치)" if own.get("float_is_estimated") else "")
    summary_rows.append({"지표": float_label, "값": f"{own['float_ratio']*100:.1f}%"})
    interp = float_ratio_interpretation(own["float_ratio"])
    if own.get("float_is_estimated"):
        interp += " — ⚠️ yfinance에 유동주식수가 없어 (총발행주식×(1-내부자보유율))로 근사 계산한 값(기관 락업 등은 반영 못 함)"
    interpretation_lines.append(("유동주식비율", interp))
if fund_ap_preview:
    total = fund_ap_preview["passive_pct"] + fund_ap_preview["active_pct"]
    if total > 0:
        summary_rows.append({
            "지표": "펀드 Passive:Active",
            "값": f"{fund_ap_preview['passive_pct']/total*100:.0f}% : {fund_ap_preview['active_pct']/total*100:.0f}%",
        })
        interpretation_lines.append((
            "펀드 Passive:Active",
            "패시브 비중이 높을수록 지수 편입/이탈에 따른 기계적 매매가 많고, 펀더멘털과 무관한 수급 영향이 큼",
        ))
if direction_preview:
    summary_rows.append({"지표": "내부자 매매 방향성", "값": direction_preview["direction"]})
    interpretation_lines.append((
        "내부자 매매 방향성",
        "단순 보유율(%)보다 최근 실제 매수/매도 방향이 더 중요한 신호일 때가 많음",
    ))

if summary_rows:
    with st.expander("📋 소유구조 종합 요약표", expanded=True):
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)
        st.caption("⚠️ 각 지표를 병치한 표일 뿐, 하나의 점수로 합산한 것이 아닙니다.")
if interpretation_lines:
    with st.expander("🔽 지표별 구간 해석"):
        for label, text in interpretation_lines:
            st.write(f"**{label}**: {text}")
    st.divider()

insider_tx = st.session_state.get("insider_tx")
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
