import sys
from pathlib import Path
from datetime import date, datetime

import numpy as np
import streamlit as st

sys.path.append(str(Path(__file__).parent))

from lib.risk import compute_stop_take_profit
from lib.peers import tier1_stats, RUNWAY_RISK_MONTHS, QUICK_RATIO_RISK
from lib.translate import to_korean
from lib.glossary import render_glossary
from lib.journal import append_entry, load_journal
from lib.config import NEWS_LOOKBACK_DAYS
from lib.page_helpers import inject_base_styles, render_wordmark
from lib.search import fetch_and_store_ticker, render_sidebar

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


def reset():
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.session_state.step = "search"
    st.rerun()


def news_headline_link(n):
    """뉴스 헤드라인을 원문 링크가 있으면 클릭 가능한 마크다운 링크로, 없으면 텍스트 그대로."""
    headline = to_korean(n["headline"])
    return f"[{headline}]({n['url']})" if n.get("url") else headline


def news_date_str(n):
    """Finnhub unix timestamp를 날짜로 변환 — 뉴스 신선도 표시용."""
    ts = n.get("datetime")
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    except (ValueError, OSError):
        return None


def evidence(msg):
    """색상으로 방향(찬성/반대)을 암시하지 않고 중립적으로 근거 한 줄을 표시."""
    st.markdown(f"- {msg}")


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


def render_technical_evidence(tag, empty_msg):
    """기술적 신호 중 tag(방향)와 일치하는 것만 나열 — Step2(반대)/Step3(지지)가 공유."""
    matched = [s for s in st.session_state.signals if s[2] == tag]
    if not matched:
        st.caption(empty_msg)
    for name, desc, _ in matched:
        evidence(f"**{name}** — {desc}")


def render_news_evidence(tag, empty_msg):
    """뉴스 중 tag(방향)와 일치하는 최근 5건 — Step2(반대)/Step3(지지)가 공유."""
    news = [n for n in st.session_state.news_classified if n["lean"] == tag]
    if not news:
        st.caption(empty_msg)
        return
    for n in news[:5]:
        date_str = news_date_str(n)
        date_part = f" ({date_str})" if date_str else ""
        evidence(f"📰 {news_headline_link(n)}{date_part} _({n['source']})_ — 매칭 키워드: {', '.join(n['matched'])}")


def render_neutral_context():
    """방향과 무관하게 항상 참고할 이벤트/유동성 정보 (실적일 임박, 저유동주식)."""
    earnings_date = st.session_state.earnings_date
    if earnings_date:
        days_left = int(np.busday_count(date.today(), earnings_date))
        if days_left <= 10:
            evidence(f"📅 실적 발표일이 {earnings_date} (D-{days_left})로 임박 — 변동성 급증 가능 (방향 무관)")
        else:
            st.caption(f"실적 발표일: {earnings_date} (D-{days_left}, 임박 아님)")

    ownership = st.session_state.ownership
    if ownership["float_ratio"] and ownership["float_ratio"] < 0.3:
        evidence(f"💧 저유동주식 — 유동주식비율 {ownership['float_ratio']*100:.1f}% (방향과 무관하게 변동성 왜곡 위험)")


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
    # 최신 순으로 일정 개수만 번역/표시 대상으로 삼는다.
    for n in st.session_state.news_classified[:30]:
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


if st.session_state.step not in ("search", "compare"):
    st.title("📉 Devil's Advocate — 스윙 트레이딩 의사결정 보조")
    st.caption("나스닥 종목의 매수/매도 관점을 한 번에 비교해서 보여주는 도구입니다. 투자 조언이 아니며, 참고용입니다.")

if isinstance(st.session_state.step, int):
    guided_labels = ["반대관점", "지지관점", "Conflict", "손절/익절", "결정메모", "최종확인", "기록완료"]
    idx = st.session_state.step - 2
    st.progress(idx / 6, text=f"정밀 검토 {idx + 1}/7 — {guided_labels[idx]}")

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
        if days_left <= 10:
            st.caption(f"📅 실적 발표일이 {earnings_date} (D-{days_left})로 임박 — 변동성 급증 가능 (방향 무관)")
    if ownership["float_ratio"] and ownership["float_ratio"] < 0.3:
        st.caption(f"💧 저유동주식 — 유동주식비율 {ownership['float_ratio']*100:.1f}% (방향과 무관하게 변동성 왜곡 위험)")

    st.divider()
    if st.button("🔍 정밀 검토 시작 (반대 관점부터 단계별로)", type="tertiary"):
        goto("intent")

# ----------------------------------------------------------------------------
# INTENT: 정밀 검토를 위한 포지션 선택
# ----------------------------------------------------------------------------
elif st.session_state.step == "intent":
    st.header(f"{st.session_state.ticker} — 포지션 선택")
    st.caption("정밀 검토는 당신이 고른 포지션의 반대 관점을 먼저 강제로 보여준 뒤 단계별로 진행됩니다.")
    intent = st.radio("포지션", ["매수 검토", "매도 검토"], index=None, horizontal=True)
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("← 비교 화면으로"):
            goto("compare")
    with col2:
        if st.button("다음: 반대 관점 확인 →", type="primary"):
            if not intent:
                st.error("포지션(매수 검토/매도 검토)을 선택해주세요.")
                st.stop()
            st.session_state.intent = intent
            goto(2)

# ----------------------------------------------------------------------------
# STEP 2: 반대 관점 강제 노출
# ----------------------------------------------------------------------------
elif st.session_state.step == 2:
    intent = st.session_state.intent
    opposite_tag = "bearish" if intent == "매수 검토" else "bullish"
    st.header(f"1. ⚠️ 반대 관점부터 확인하세요 ({intent}에 대한 회의적 근거)")
    st.warning("이 단계를 건너뛸 수 없습니다. 아래 근거를 먼저 확인해야 다음 단계로 진행됩니다.")
    st.caption("색상으로 유불리를 표시하지 않습니다 — 아래는 모두 당신의 의도(위 제목)와 반대되는 근거입니다.")
    render_glossary(["RSI", "MACD", "이동평균(MA)", "볼린저밴드", "ATR"], title="ℹ️ 기술적 지표 설명")

    st.subheader("🔧 기술적 근거")
    render_technical_evidence(opposite_tag, "기술적 지표상 뚜렷한 반대 근거는 없습니다.")

    st.subheader("⚠️ 이벤트·유동성 리스크")
    st.caption("방향과 무관한 일반 참고 항목 + 당신의 의도와 반대되는 리스크 항목")
    render_neutral_context()
    context_items = compute_flagged_context()
    risk_items = filter_context(context_items, "risk", opposite_tag)
    for msg in risk_items:
        evidence(msg)
    if not risk_items:
        st.caption("반대 방향 이벤트·유동성 리스크 없음")

    st.subheader("💰 밸류에이션 근거")
    valuation_items = filter_context(context_items, "valuation", opposite_tag)
    if valuation_items:
        for msg in valuation_items:
            evidence(msg)
    else:
        st.caption("반대 방향 밸류에이션 근거 없음")

    st.subheader("📰 정성적 근거 (뉴스·애널리스트)")
    st.caption("⚠️ 뉴스 톤은 키워드 매칭 기반 근사치입니다 (정밀 감성분석 아님, 원문 직접 확인 권장)")

    analyst_trend = st.session_state.analyst_trend
    if analyst_trend and analyst_trend["lean"] == opposite_tag:
        evidence(
            f"📊 애널리스트 의견({analyst_trend['period']}): 매수 {analyst_trend['strongBuy']+analyst_trend['buy']} / "
            f"중립 {analyst_trend['hold']} / 매도 {analyst_trend['strongSell']+analyst_trend['sell']} "
            f"— {'회의적' if opposite_tag=='bearish' else '긍정적'} 쪽으로 쏠림"
        )

    render_news_evidence(opposite_tag, f"최근 {NEWS_LOOKBACK_DAYS}일 뉴스 중 반대 관점 키워드 매칭 없음")

    confirmed = st.checkbox("위 반대 관점 근거를 확인했습니다.")
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("← 비교 화면으로"):
            goto("compare")
    with col2:
        if st.button("다음: 지지 관점 확인 →", type="primary", disabled=not confirmed):
            goto(3)

# ----------------------------------------------------------------------------
# STEP 3: 지지 관점
# ----------------------------------------------------------------------------
elif st.session_state.step == 3:
    intent = st.session_state.intent
    same_tag = "bullish" if intent == "매수 검토" else "bearish"
    st.header(f"2. {intent}를 지지하는 근거")
    st.caption("색상으로 유불리를 표시하지 않습니다 — 아래는 모두 당신의 의도를 지지하는 근거입니다.")

    st.subheader("🔧 기술적 근거")
    render_technical_evidence(same_tag, "기술적 지표상 뚜렷한 지지 근거는 없습니다.")

    neutral_signals = [s for s in st.session_state.signals if s[2] == "neutral"]
    for name, desc, _ in neutral_signals:
        st.caption(f"(중립) {name} — {desc}")

    context_items = compute_flagged_context()
    risk_items = filter_context(context_items, "risk", same_tag)
    if risk_items:
        st.subheader("⚠️ 이벤트·유동성 근거")
        for msg in risk_items:
            evidence(msg)

    valuation_items = filter_context(context_items, "valuation", same_tag)
    if valuation_items:
        st.subheader("💰 밸류에이션 근거")
        for msg in valuation_items:
            evidence(msg)

    st.subheader("📰 정성적 근거 (뉴스·애널리스트)")
    st.caption("⚠️ 뉴스 톤은 키워드 매칭 기반 근사치입니다 (정밀 감성분석 아님, 원문 직접 확인 권장)")

    analyst_trend = st.session_state.analyst_trend
    if analyst_trend and analyst_trend["lean"] == same_tag:
        evidence(
            f"📊 애널리스트 의견({analyst_trend['period']}): 매수 {analyst_trend['strongBuy']+analyst_trend['buy']} / "
            f"중립 {analyst_trend['hold']} / 매도 {analyst_trend['strongSell']+analyst_trend['sell']} "
            f"— {'긍정적' if same_tag=='bullish' else '회의적'} 쪽으로 쏠림"
        )
    elif analyst_trend:
        st.caption(
            f"애널리스트 의견({analyst_trend['period']}): 매수 {analyst_trend['strongBuy']+analyst_trend['buy']} / "
            f"중립 {analyst_trend['hold']} / 매도 {analyst_trend['strongSell']+analyst_trend['sell']} — 중립/혼조"
        )

    render_news_evidence(same_tag, f"최근 {NEWS_LOOKBACK_DAYS}일 뉴스 중 지지 관점 키워드 매칭 없음")

    news_summary = st.session_state.news_summary
    st.caption(
        f"뉴스 톤 요약 (최근 {NEWS_LOOKBACK_DAYS}일, 총 {news_summary['total']}건): "
        f"긍정 {news_summary['bullish']} / 부정 {news_summary['bearish']} / 중립 {news_summary['neutral']}"
    )

    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("← 반대 관점 다시 보기"):
            goto(2)
    with col2:
        if st.button("다음: Conflict Board →", type="primary"):
            goto(4)

# ----------------------------------------------------------------------------
# STEP 4: Conflict Board
# ----------------------------------------------------------------------------
elif st.session_state.step == 4:
    st.header("3. Conflict Board — 관점이 충돌하는 지점")
    st.caption("점수를 합산하지 않습니다. 매수 관점과 매도 관점을 나눠서 병치합니다.")

    lines = collect_bull_bear_lines()
    col1, col2 = st.columns(2)
    with col1:
        render_side("🔵 매수 관점", lines["bullish"])
    with col2:
        render_side("🟠 매도 관점", lines["bearish"])

    has_bull = any(lines["bullish"].values())
    has_bear = any(lines["bearish"].values())
    if has_bull and has_bear:
        st.warning("⚠️ 매수 관점과 매도 관점의 근거가 둘 다 있습니다 — 아래 손절/익절에서 보수적으로 접근하는 것을 권장합니다.")

    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("← 지지 관점 다시 보기"):
            goto(3)
    with col2:
        if st.button("다음: 손절/익절 →", type="primary"):
            goto(5)

# ----------------------------------------------------------------------------
# STEP 5: 자동 산출 + 확인 강제 (손절/익절)
# ----------------------------------------------------------------------------
elif st.session_state.step == 5:
    st.header("4. 손절가 / 익절가 (기술적 지표 반영)")

    ind = st.session_state.ind
    info = st.session_state.info
    live_price = info.get("currentPrice") or info.get("regularMarketPrice") or ind["close"]
    st.metric("현재가", f"${live_price:.2f}")
    st.caption("⚠️ 데이터 제공사 기준 시세이며, 최대 1시간 캐시됩니다 — 실제 체결가와 다를 수 있으니 매매 직전 브로커 화면에서 재확인하세요.")

    if st.session_state.intent == "매수 검토":
        entry = st.number_input(
            "진입가 ($) — 실제로 매수하려는(또는 매수한) 가격을 입력하세요", value=round(float(live_price), 2), format="%.2f",
        )
    else:
        entry = live_price
        st.caption(
            "매도 검토 = 신규 공매도가 아니라 '지금 보유 중인 포지션을 청산할지' 판단입니다. "
            "아래 값은 새 진입가가 아니라 **오늘 팔지 않고 계속 들고 갈 경우** 기준으로, "
            "손절가 아래로 빠지면 그때는 정리하고 익절가 위로 가면 목표 도달로 보는 기준선입니다."
        )

    rt = compute_stop_take_profit(entry, ind)

    with st.expander("📐 산출 근거 펼쳐보기 (필수)", expanded=True):
        st.write("**손절가 후보 (MAX 채택 = 가장 보수적)**")
        for label, val in rt["stop_candidates"].items():
            marker = " ← 채택" if label == rt["stop_label"] else ""
            st.write(f"- {label}: ${val:.2f}{marker}")
        st.write("**익절가 후보 (MIN 채택 = 가장 보수적, 물량 50%)**")
        for label, val in rt["tp_candidates"].items():
            marker = " ← 채택" if label == rt["tp_label"] else ""
            st.write(f"- {label}: ${val:.2f}{marker}")
        st.caption("⚠️ 이 값은 하나의 계산 방식(참고용)일 뿐, 보장된 정답이 아닙니다.")

    col1, col2 = st.columns(2)
    with col1:
        stop = st.number_input("손절가 ($)", value=round(rt["stop"], 2), format="%.2f")
    with col2:
        tp = st.number_input("보수적 익절가 (50% 물량, $)", value=round(rt["take_profit"], 2), format="%.2f")
    st.caption("나머지 50% 물량은 추격손절(Chandelier Exit)로 트레일링하며 목표가를 미리 정하지 않습니다.")
    st.caption("매수 수량·자금 배분은 이 도구가 다루지 않습니다 — 개인 자금관리는 사용자 몫입니다.")

    rationale_confirmed = st.checkbox("위 산출 근거를 확인했습니다.")
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("← Conflict Board로"):
            goto(4)
    with col2:
        if st.button("다음: 결정 이유 메모 →", type="primary", disabled=not rationale_confirmed):
            st.session_state.entry_price = entry
            st.session_state.stop = stop
            st.session_state.take_profit = tp
            goto(6)

# ----------------------------------------------------------------------------
# STEP 6: 결정 이유 메모 (선택)
# ----------------------------------------------------------------------------
elif st.session_state.step == 6:
    st.header("5. 이 결정을 내린 이유")
    memo = st.text_area(
        "왜 지금 이 포지션을 검토하고 있나요? (선택 입력)",
        value=st.session_state.get("memo", ""), height=120,
    )
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("← 이전 단계로"):
            goto(5)
    with col2:
        if st.button("다음: 최종 확인 →", type="primary"):
            st.session_state.memo = memo.strip()
            goto(7)

# ----------------------------------------------------------------------------
# STEP 7: 최종 확인
# ----------------------------------------------------------------------------
elif st.session_state.step == 7:
    st.header("6. 최종 확인")
    st.write(f"**티커:** {st.session_state.ticker}  |  **의도:** {st.session_state.intent}")
    c1, c2 = st.columns(2)
    c1.metric("손절가", f"${st.session_state.stop:.2f}")
    c2.metric("보수적 익절가 (50%)", f"${st.session_state.take_profit:.2f}")
    st.write(f"**결정 이유 메모:** {st.session_state.memo or '(작성 안 함)'}")
    st.info("나머지 50% 물량은 추격손절로 트레일링, 목표가 없음.")

    col1, col2, col3 = st.columns([1, 2, 2])
    with col1:
        if st.button("← 메모 수정"):
            goto(6)
    with col2:
        if st.button("✅ 그대로 진행 (기록)", type="primary"):
            append_entry({
                "ticker": st.session_state.ticker, "intent": st.session_state.intent,
                "entry_price": st.session_state.entry_price, "stop": st.session_state.stop,
                "take_profit": st.session_state.take_profit, "memo": st.session_state.memo,
            })
            goto(8)
    with col3:
        if st.button("✏️ 값 수정 후 진행"):
            goto(5)

# ----------------------------------------------------------------------------
# STEP 8: 완료 + 매매일지
# ----------------------------------------------------------------------------
elif st.session_state.step == 8:
    st.header("7. ✅ 매매일지에 기록되었습니다")
    st.caption("실제 주문은 브로커에서 직접 실행하세요. 이 도구는 자동매매를 하지 않습니다.")
    st.dataframe(load_journal(), use_container_width=True)
    if st.button("새 종목 분석하기"):
        reset()

if st.session_state.step != "search":
    st.divider()
    if st.button("🔄 처음부터 다시 (전체 초기화)"):
        reset()
