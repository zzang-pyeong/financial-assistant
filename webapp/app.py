import sys
from pathlib import Path
from datetime import date

import numpy as np
import streamlit as st

sys.path.append(str(Path(__file__).parent))

from lib._shared_core.peers import tier1_stats, RUNWAY_RISK_MONTHS, QUICK_RATIO_RISK
from lib._shared_core.translate import to_korean
from lib._shared_core.page_helpers import inject_base_styles, render_wordmark, news_date_str
from lib._shared_core.search import fetch_and_store_ticker, render_sidebar
from lib._shared_core.config import BOARD_NEWS_LIMIT
from lib._shared_core.charts import render_price_chart_figure, PERIOD_OPTIONS, PLOTLY_CONFIG

if "step" not in st.session_state:
    st.session_state.step = "search"

st.set_page_config(
    page_title="EnterTicker",
    layout="centered" if st.session_state.step == "search" else "wide",
)
inject_base_styles()


def goto(step):
    st.session_state.step = step
    st.rerun()


def news_headline_link(n):
    """뉴스 헤드라인을 원문 링크가 있으면 클릭 가능한 마크다운 링크로, 없으면 텍스트 그대로."""
    headline = to_korean(n["headline"])
    return f"[{headline}]({n['url']})" if n.get("url") else headline


def compute_flagged_context():
    """이벤트/유동성/밸류에이션 등 부가 근거를 (문구, 방향태그, 카테고리)로 반환.
    방향태그가 있어야 Step2/3에서 사용자가 선택한 포지션 방향에 맞춰 필터링할 수 있다
    (기존엔 방향 무관하게 항상 Step2에만 나와서, 매도 검토 사용자에게는 반대로 보였음)."""
    items = []  # (message, tag, category) — category: "risk" | "valuation"

    if not st.session_state.regime_favorable:
        items.append((
            f"📉 시장 국면 비우호적 — QQQ({st.session_state.qqq_price:.2f}) < MA200({st.session_state.qqq_ma200:.2f})",
            "bearish", "risk",
        ))

    ownership = st.session_state.ownership
    if ownership["short_pct_float"] and ownership["short_pct_float"] > 0.1:
        items.append((
            f"🩳 공매도 비율 {ownership['short_pct_float']*100:.1f}% — 주목할 만한 수준",
            "bearish", "risk",
        ))

    peer_stats = tier1_stats(st.session_state.peer_data["peers"])
    fwd_pe = st.session_state.info.get("forwardPE")
    if peer_stats and isinstance(fwd_pe, (int, float)) and fwd_pe > 0:
        multiple = fwd_pe / peer_stats["mean"]
        if multiple > 1.5:
            items.append((
                f"💰 포워드 PER {fwd_pe:.1f}가 동종 peer 평균({peer_stats['mean']:.1f}, n={peer_stats['n']})의 "
                f"{multiple:.1f}배 — 고평가 논란",
                "bearish", "valuation",
            ))

    target_health = st.session_state.target_health
    if not target_health["fcf_positive"] and target_health["runway_months"] is not None \
            and target_health["runway_months"] < RUNWAY_RISK_MONTHS:
        items.append((
            f"⏳ 현금 런웨이 {target_health['runway_months']:.1f}개월 — 단기 증자/희석 가능성 (PER과 무관한 생존 리스크)",
            "bearish", "risk",
        ))
    if isinstance(target_health["quick_ratio"], (int, float)) and target_health["quick_ratio"] < QUICK_RATIO_RISK:
        items.append((
            f"💧 당좌비율 {target_health['quick_ratio']:.2f} — 단기 채무 대비 현금성자산 크게 부족",
            "bearish", "risk",
        ))

    return items


def filter_context(context_items, category, tag):
    """compute_flagged_context() 결과에서 카테고리·방향이 일치하는 문구만 뽑는다."""
    return [msg for msg, t, cat in context_items if cat == category and t == tag]


def collect_bull_bear_lines():
    """기술적/이벤트·유동성/밸류에이션/정성적 근거를 매수 관점·매도 관점으로 나눠서 반환.
    포지션 의도와 무관하게 항상 같은 내용 — '비교 보기'와 Conflict Board가 함께 쓴다."""
    signals = st.session_state.signals
    tech_bull = [f"{name}: {desc}" for name, desc, tag in signals if tag == "bullish"]
    tech_bear = [f"{name}: {desc}" for name, desc, tag in signals if tag == "bearish"]

    analyst_trend = st.session_state.analyst_trend
    qual_bull, qual_bear = [], []
    if analyst_trend and analyst_trend["lean"] != "neutral":
        line = (f"애널리스트 의견({analyst_trend['period']}): 매수 "
                f"{analyst_trend['strongBuy']+analyst_trend['buy']} / 매도 "
                f"{analyst_trend['strongSell']+analyst_trend['sell']}")
        (qual_bull if analyst_trend["lean"] == "bullish" else qual_bear).append(line)

    # 헤드라인 하나당 번역 API 호출 1회 — 전체를 다 돌면(수백 건) 화면이 오래 멈춰 보이므로
    # 최신 순으로 일정 개수만 번역/표시 대상으로 삼는다. 이 개수는 fetch_and_store_ticker()가
    # 수집 단계에서 미리 병렬 번역해두는 개수(BOARD_NEWS_LIMIT)와 반드시 같아야 한다 —
    # 여기서 더 많이 돌면 초과분이 캐시 미스가 나서 렌더 도중 순차 요청이 다시 발생한다.
    for n in st.session_state.news_classified[:BOARD_NEWS_LIMIT]:
        date_str = news_date_str(n)
        date_part = f" ({date_str})" if date_str else ""
        line = f"뉴스: {news_headline_link(n)}{date_part}"
        if n["lean"] == "bullish":
            qual_bull.append(line)
        elif n["lean"] == "bearish":
            qual_bear.append(line)

    context_items = compute_flagged_context()

    return {
        "bullish": {
            "기술적 근거": tech_bull,
            "이벤트·유동성": filter_context(context_items, "risk", "bullish"),
            "밸류에이션": filter_context(context_items, "valuation", "bullish"),
            "정성적 근거": qual_bull,
        },
        "bearish": {
            "기술적 근거": tech_bear,
            "이벤트·유동성": filter_context(context_items, "risk", "bearish"),
            "밸류에이션": filter_context(context_items, "valuation", "bearish"),
            "정성적 근거": qual_bear,
        },
    }


def render_side(title, groups, preview_count=5):
    st.subheader(title)
    for group_name, lines in groups.items():
        st.markdown(f"**{group_name}**")
        if lines:
            visible, rest = lines[:preview_count], lines[preview_count:]
            for line in visible:
                st.markdown(f"- {line}")
            if rest:
                with st.expander(f"더보기 ({len(rest)}개)"):
                    for line in rest:
                        st.markdown(f"- {line}")
        else:
            st.caption("없음")


if "ticker" in st.session_state:
    with st.sidebar:
        render_sidebar()

# ----------------------------------------------------------------------------
# SEARCH: 티커 검색 — 포지션 선택 없이 바로 비교 화면으로
# ----------------------------------------------------------------------------
if st.session_state.step == "search":
    render_wordmark("Enter", "Ticker", size="3.4rem", align="center", margin="8vh 0 2rem 0", sep="")

    st.markdown(
        '<style>'
        '[data-testid="stForm"] {border: none; padding: 0;}'
        '[data-testid="stForm"] [data-testid="stHorizontalBlock"] {'
        '  gap: 0; align-items: center; background: rgb(240, 242, 246);'
        '  border-radius: 28px; padding: 4px 4px 4px 20px;'
        '}'
        '[data-testid="stForm"] [data-testid="stTextInput"] > div {'
        '  border: none; background: transparent; box-shadow: none;'
        '}'
        '[data-testid="stForm"] [data-testid="stTextInput"] input {'
        '  background: transparent; height: 42px; font-size: 1.05rem;'
        '}'
        '[data-testid="stForm"] [data-testid="stFormSubmitButton"] button {'
        '  border-radius: 24px; height: 42px; width: 100%;'
        '}'
        '</style>',
        unsafe_allow_html=True,
    )
    with st.form("search_form"):
        col_input, col_btn = st.columns([6, 1])
        with col_input:
            raw_input = st.text_input(
                "티커 또는 기업명 (한글/영문 모두 가능, 예: NVDA, Nvidia, 엔비디아)",
                value=st.session_state.get("ticker", ""),
                label_visibility="collapsed",
                placeholder="티커 또는 기업명을 입력하세요 (예: NVDA, Nvidia, 엔비디아)",
            )
        with col_btn:
            submitted = st.form_submit_button("Enter", type="primary", use_container_width=True)

    if submitted and fetch_and_store_ticker(raw_input):
        goto("compare")

# ----------------------------------------------------------------------------
# COMPARE: 매수 관점 vs 매도 관점 비교 (핵심 기능 — 포지션 선택 없이 바로 확인)
# ----------------------------------------------------------------------------
elif st.session_state.step == "compare":
    render_wordmark("Conflict", "Board", size="2.8rem", align="center", margin="1vh 0 2rem 0")

    # 근거를 읽기 전에 지금 가격이 어떤 모양인지부터 한눈에 보이게 — 상세 기간·분봉은
    # Price Chart 페이지가 따로 있으니 여기서는 최근 1개월 일봉만 가볍게 보여준다.
    st.plotly_chart(
        render_price_chart_figure(st.session_state.df, PERIOD_OPTIONS["1개월"]),
        use_container_width=True, config=PLOTLY_CONFIG,
    )
    st.caption("최근 1개월 일봉입니다 — 더 긴 기간·분봉은 Price Chart 페이지에서 볼 수 있습니다.")

    lines = collect_bull_bear_lines()
    col1, col2 = st.columns(2)
    with col1:
        render_side("🔵 매수 관점", lines["bullish"])
    with col2:
        render_side("🟠 매도 관점", lines["bearish"])

    # 방향과 무관한 참고사항은 실제로 급한 것만(실적 임박·저유동) 노출 — 평소엔 생략
    earnings_date = st.session_state.earnings_date
    ownership = st.session_state.ownership
    if earnings_date:
        days_left = int(np.busday_count(date.today(), earnings_date))
        if 0 <= days_left <= 10:
            st.caption(f"📅 실적 발표일이 {earnings_date} (D-{days_left})로 임박 — 변동성 급증 가능 (방향 무관)")
    if ownership["float_ratio"] and ownership["float_ratio"] < 0.3:
        st.caption(f"💧 저유동주식 — 유동주식비율 {ownership['float_ratio']*100:.1f}% (방향과 무관하게 변동성 왜곡 위험)")

