import sys
from pathlib import Path

import streamlit as st

sys.path.append(str(Path(__file__).parent.parent))

from lib.peers import tier1_stats, runway_interpretation, quick_ratio_interpretation, roe_interpretation
from lib.glossary import render_glossary
from lib.page_helpers import require_analysis

st.set_page_config(page_title="섹터 Peer 비교 — Devil's Advocate", layout="wide")
require_analysis()

ticker = st.session_state.ticker
st.title(f"📊 {ticker} — 섹터 Peer 비교")
st.caption("병치만 하고 점수화하지 않습니다 (원칙 B) — 의사결정 흐름과 분리된 참고용 큰 화면 뷰입니다.")
st.page_link("app.py", label="← 메인 흐름으로 돌아가기", icon="🏠")
st.divider()

peer_data = st.session_state.peer_data
fwd_pe = st.session_state.info.get("forwardPE")
st.write(f"대상 종목 Forward PE: **{fwd_pe:.1f}**" if isinstance(fwd_pe, (int, float)) else "Forward PE: N/A")
if peer_data["dict_name"]:
    st.caption(f"자동 판별된 섹터 키워드 그룹: {peer_data['dict_name']} ({', '.join(peer_data['target_matches'])})")
else:
    st.caption("자동 판별된 니치 섹터 키워드 없음 — 전체 peer가 Tier2로 표시됨")

stats = tier1_stats(peer_data["peers"])
if stats:
    label = "평균" if stats["reliable"] else f"평균(n={stats['n']}, 표본 부족)"
    st.write(f"Tier1(진짜 동종) {label}: **{stats['mean']:.1f}** (중앙값 {stats['median']:.1f}, n={stats['n']})")
    if isinstance(fwd_pe, (int, float)) and fwd_pe > 0:
        st.write(f"→ 대상 종목은 Tier1 평균의 **{fwd_pe/stats['mean']:.1f}배**")
else:
    st.caption("Tier1 유효 forward PE 표본 없음")
st.caption("⚠️ PER은 적자 섹터에서 무력화됨(실증 확인) — EV/Revenue·유동성·런웨이를 함께 참고하세요")

target_health = st.session_state.target_health
with st.expander(f"{ticker} 재무 건전성 (Peer 비교 보완)", expanded=True):
    ev_str = f"{target_health['ev_revenue']:.1f}" if isinstance(target_health['ev_revenue'], (int, float)) else "N/A"
    qr = target_health['quick_ratio']
    st.write(f"EV/Revenue: **{ev_str}**  ·  당좌비율: **{qr:.2f}**" if isinstance(qr, (int, float)) else f"EV/Revenue: **{ev_str}**")
    st.write(f"현금 런웨이: **{runway_interpretation(target_health)}**")
    if isinstance(qr, (int, float)):
        st.caption(f"당좌비율 판정: {quick_ratio_interpretation(qr)}")
    pbr_str = f"{target_health['pbr']:.2f}" if isinstance(target_health['pbr'], (int, float)) else "N/A"
    de_str = f"{target_health['debt_to_equity']:.1f}" if isinstance(target_health['debt_to_equity'], (int, float)) else "N/A"
    st.write(f"PBR: **{pbr_str}**  ·  부채비율(D/E): **{de_str}**")
    st.write(f"ROE: **{roe_interpretation(target_health['roe'], target_health['debt_to_equity'])}**")

render_glossary(
    ["Forward PER", "PBR", "ROE", "EV/Revenue", "유동비율·당좌비율", "부채비율(D/E)", "현금 런웨이"],
    title="ℹ️ 펀더멘털 지표 설명",
)
