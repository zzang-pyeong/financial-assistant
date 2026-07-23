import sys
from pathlib import Path

import streamlit as st

sys.path.append(str(Path(__file__).parent.parent))

from lib.peers import (
    tier1_stats, runway_interpretation, quick_ratio_interpretation, roe_interpretation,
)
from lib.ownership import (
    insider_trade_direction, float_ratio_interpretation, institution_pct_interpretation,
)
from lib.translate import to_korean
from lib.glossary import render_glossary
from lib.config import ANALYST_NEWS_LOOKBACK_DAYS

st.set_page_config(page_title="상세 데이터 — Devil's Advocate", layout="wide")

if st.session_state.get("step", 1) < 2 or "peer_data" not in st.session_state:
    st.title("📊 상세 데이터")
    st.info("먼저 메인 페이지에서 티커를 분석해주세요.")
    st.page_link("app.py", label="← 메인 페이지로", icon="🏠")
    st.stop()

ticker = st.session_state.ticker
st.title(f"📊 {ticker} 상세 데이터")
st.caption("병치만 하고 점수화하지 않습니다 (원칙 B) — 의사결정 흐름과 분리된 참고용 큰 화면 뷰입니다.")
st.page_link("app.py", label="← 메인 흐름으로 돌아가기", icon="🏠")
st.divider()

col_left, col_right = st.columns(2)

# ---------------------------------------------------------------- 왼쪽: Peer/재무
with col_left:
    st.header("섹터 Peer 비교")
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

    st.subheader("Peer 목록")
    for p in sorted(peer_data["peers"], key=lambda x: x["tier"]):
        tier_str = "🟢Tier1" if p["tier"] == 1 else "⚪Tier2"
        pe_str = f"{p['forwardPE']:.1f}" if isinstance(p["forwardPE"], (int, float)) else "N/A"
        h = p["health"]
        ev_str = f"{h['ev_revenue']:.1f}" if isinstance(h['ev_revenue'], (int, float)) else "·"
        qr_str = f"{h['quick_ratio']:.2f}" if isinstance(h['quick_ratio'], (int, float)) else "·"
        runway_str = "흑자" if h["fcf_positive"] else (f"{h['runway_months']:.0f}개월" if h["runway_months"] is not None else "·")
        st.write(f"{tier_str} **{p['ticker']}** ({p['name']}) — FwdPE {pe_str} · EV/Rev {ev_str} · 당좌 {qr_str} · 런웨이 {runway_str}")

    render_glossary(
        ["Forward PER", "PBR", "ROE", "EV/Revenue", "유동비율·당좌비율", "부채비율(D/E)", "현금 런웨이"],
        title="ℹ️ 펀더멘털 지표 설명",
    )

# ---------------------------------------------------------------- 오른쪽: 소유구조/뉴스
with col_right:
    st.header("소유구조")
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

    st.header("애널리스트 관련 뉴스 (근사치)")
    st.caption(
        f"최근 {ANALYST_NEWS_LOOKBACK_DAYS}일 뉴스 중 'upgrade/price target' 등 키워드가 있는 것만 필터링. "
        "⚠️ 실제 매수/매도 집계의 확정된 근거는 아니며, 관련 있어 보이는 뉴스일 뿐입니다."
    )
    analyst_news = st.session_state.get("analyst_news", [])
    if analyst_news:
        for n in analyst_news[:8]:
            st.write(f"- {to_korean(n['headline'])}")
            st.caption(f"매칭 키워드: {', '.join(n['matched'])} · [원문]({n['url']})")
    else:
        st.caption("해당 기간 내 애널리스트 관련 뉴스 없음")

st.divider()

# ---------------------------------------------------------------- 전체 폭: 기업 이벤트 뉴스
st.header("주요 기업 이벤트 뉴스 (M&A · 경영진 교체 · 신규 계약/파트너십)")
st.caption(
    f"최근 {ANALYST_NEWS_LOOKBACK_DAYS}일 뉴스 중 인수합병·경영진 교체·신규 계약 관련 키워드가 "
    "있는 것만 근사 필터링한 것입니다. ⚠️ 키워드 매칭 기반 근사치이며, 정밀 이벤트 추출이 아닙니다."
)
corporate_events = st.session_state.get("corporate_events", [])
if corporate_events:
    for ev in corporate_events[:10]:
        cats = ", ".join(f"{c['category']}({', '.join(c['matched'])})" for c in ev["categories"])
        st.write(f"- {to_korean(ev['headline'])}")
        st.caption(f"분류: {cats} · _({ev['source']})_ · [원문]({ev['url']})")
else:
    st.caption("해당 기간 내 M&A·경영진 교체·신규 계약 관련 뉴스 없음")
