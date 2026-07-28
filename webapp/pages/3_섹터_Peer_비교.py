import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.append(str(Path(__file__).parent.parent))

from lib._shared_core.peers import (
    tier1_stats, runway_interpretation, quick_ratio_interpretation, roe_interpretation,
    current_ratio_interpretation, format_pct, ev_ebitda_interpretation,
    financial_characteristics_comment,
)
from lib._shared_core.glossary import render_glossary
from lib._shared_core.page_helpers import require_analysis, inject_base_styles, render_wordmark, render_ticker_header
from lib._shared_core.search import render_sidebar

_BASIS_KO = {
    "same industry": "동일 산업",
    "same sector + cap band": "동일 섹터·시총",
    "niche keyword": "니치 키워드",
    "": "—",
}

st.set_page_config(page_title="Peer Compare — EnterTicker", layout="wide")
inject_base_styles()
require_analysis()

with st.sidebar:
    render_sidebar()

ticker = st.session_state.ticker
with st.container(key="page_header"):
    render_wordmark("Peer", "Compare", align="center")
    render_ticker_header(ticker)
st.divider()

peer_data = st.session_state.peer_data
fwd_pe = st.session_state.info.get("forwardPE")
st.write(f"대상 종목 Forward PE: **{fwd_pe:.1f}**" if isinstance(fwd_pe, (int, float)) else "Forward PE: N/A")
if peer_data["dict_name"]:
    st.caption(f"자동 판별된 섹터 키워드 그룹: {peer_data['dict_name']} ({', '.join(peer_data['target_matches'])})")
else:
    st.caption('')

stats = tier1_stats(peer_data["peers"])
if stats:
    label = "평균" if stats["reliable"] else f"평균(n={stats['n']}, 표본 부족)"
    st.write(f"Tier1(진짜 동종) {label}: **{stats['mean']:.1f}** (중앙값 {stats['median']:.1f}, n={stats['n']})")
    if isinstance(fwd_pe, (int, float)) and fwd_pe > 0:
        st.write(f"→ 대상 종목은 Tier1 평균의 **{fwd_pe/stats['mean']:.1f}배**")
else:
    st.caption("Tier1 유효 forward PE 표본 없음")
st.caption('')

target_health = st.session_state.target_health
with st.expander(f"{ticker} 재무 건전성 (Peer 비교 보완)", expanded=True):
    comment = financial_characteristics_comment(target_health)
    if comment:
        st.info(f"🧾 {comment}")
        st.caption(
           ''
        )
    ev_str = f"{target_health['ev_revenue']:.1f}" if isinstance(target_health['ev_revenue'], (int, float)) else "N/A"
    qr = target_health['quick_ratio']
    st.write(f"EV/Revenue: **{ev_str}**  ·  당좌비율: **{qr:.2f}**" if isinstance(qr, (int, float)) else f"EV/Revenue: **{ev_str}**")
    st.write(f"EV/EBITDA: **{ev_ebitda_interpretation(target_health['ev_ebitda'])}**")
    st.write(f"현금 런웨이: **{runway_interpretation(target_health)}**")
    if isinstance(qr, (int, float)):
        st.caption(f"당좌비율 판정: {quick_ratio_interpretation(qr)}")
    cr = target_health['current_ratio']
    if isinstance(cr, (int, float)):
        st.write(f"유동비율: **{cr:.2f}** — {current_ratio_interpretation(cr)}")
    pbr_str = f"{target_health['pbr']:.2f}" if isinstance(target_health['pbr'], (int, float)) else "N/A"
    de_str = f"{target_health['debt_to_equity']:.1f}" if isinstance(target_health['debt_to_equity'], (int, float)) else "N/A"
    st.write(f"PBR: **{pbr_str}**  ·  부채비율(D/E): **{de_str}**")
    st.write(f"ROE: **{roe_interpretation(target_health['roe'], target_health['debt_to_equity'])}**")
    om_str = format_pct(target_health['operating_margin']) or "N/A"
    gm_str = format_pct(target_health['gross_margin']) or "N/A"
    st.write(f"영업이익률: **{om_str}**  ·  매출총이익률: **{gm_str}**")
    rg_str = format_pct(target_health['revenue_growth_yoy']) or "N/A"
    st.write(f"매출성장률(YoY): **{rg_str}**")

with st.expander("📋 전체 Peer 목록 (Tier1+Tier2)"):
    rows = []
    for p in sorted(peer_data["peers"], key=lambda x: x["tier"]):
        h = p["health"]
        runway_str = "흑자" if h["fcf_positive"] else (f"{h['runway_months']:.0f}개월" if h["runway_months"] is not None else "·")
        rows.append({
            "Tier": "Tier1" if p["tier"] == 1 else "Tier2",
            "근거": _BASIS_KO.get(p.get("tier_basis", ""), "—"),
            "티커": p["ticker"],
            "기업명": p["name"],
            "Forward PE": round(p["forwardPE"], 1) if isinstance(p["forwardPE"], (int, float)) else None,
            "EV/Revenue": round(h["ev_revenue"], 1) if isinstance(h["ev_revenue"], (int, float)) else None,
            "EV/EBITDA": ev_ebitda_interpretation(h["ev_ebitda"]),
            "당좌비율": round(h["quick_ratio"], 2) if isinstance(h["quick_ratio"], (int, float)) else None,
            "유동비율": round(h["current_ratio"], 2) if isinstance(h["current_ratio"], (int, float)) else None,
            "영업이익률": format_pct(h["operating_margin"]),
            "매출총이익률": format_pct(h["gross_margin"]),
            "매출성장률(YoY)": format_pct(h["revenue_growth_yoy"]),
            "현금 런웨이": runway_str,
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

render_glossary(
    [
        "Forward PER", "PBR", "ROE", "EV/Revenue", "EV/EBITDA", "유동비율·당좌비율",
        "부채비율(D/E)", "영업이익률", "매출총이익률", "매출성장률(YoY)", "현금 런웨이",
    ],
    title="ℹ️ 펀더멘털 지표 설명",
)
