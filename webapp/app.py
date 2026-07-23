import sys
from pathlib import Path
from datetime import date, timedelta

import numpy as np
import streamlit as st

sys.path.append(str(Path(__file__).parent))

from lib.data import (
    get_price_history, get_yf_info, get_yf_calendar, get_finnhub_recommendation_trends,
    get_finnhub_company_news, resolve_ticker,
)
from lib.indicators import compute_indicators, classify_indicator_signals
from lib.risk import compute_stop_take_profit
from lib.peers import (
    classify_peers, tier1_stats, get_financial_health,
    RUNWAY_RISK_MONTHS, QUICK_RATIO_RISK,
)
from lib.ownership import (
    get_ownership_summary, get_fund_level_active_passive, get_firm_level_holders,
    get_recent_insider_transactions,
)
from lib.qualitative import (
    classify_news_tone, news_tone_summary, classify_analyst_trend,
    filter_analyst_related_news, filter_corporate_event_news,
)
from lib.translate import to_korean
from lib.glossary import render_glossary
from lib.journal import append_entry, load_journal
from lib.config import NEWS_LOOKBACK_DAYS, ANALYST_NEWS_LOOKBACK_DAYS
from lib.charts import render_price_chart_figure, PERIOD_OPTIONS

st.set_page_config(page_title="Devil's Advocate — 스윙 트레이딩 의사결정 보조", layout="wide")

if "step" not in st.session_state:
    st.session_state.step = 1


def goto(step):
    st.session_state.step = step
    st.rerun()


def reset():
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.session_state.step = 1
    st.rerun()


def news_headline_link(n):
    """뉴스 헤드라인을 원문 링크가 있으면 클릭 가능한 마크다운 링크로, 없으면 텍스트 그대로."""
    headline = to_korean(n["headline"])
    return f"[{headline}]({n['url']})" if n.get("url") else headline


st.title("📉 Devil's Advocate — 스윙 트레이딩 의사결정 보조")
st.caption("이 도구는 매매 신호를 대신 결정해주지 않습니다. 투자 조언이 아니며, 참고용 계산 보조 도구입니다.")

steps_label = ["1.티커/의도", "2.반대관점", "3.지지관점", "4.Conflict", "5.손절/익절", "6.결정메모", "7.최종확인", "8.기록완료"]
st.progress((st.session_state.step - 1) / 7, text=f"진행 단계: {steps_label[st.session_state.step - 1]}")

if st.session_state.step >= 2:
    with st.expander(f"📈 {st.session_state.ticker} 최근 주가 차트", expanded=True):
        period_label = st.radio(
            "기간", list(PERIOD_OPTIONS.keys()), index=2, horizontal=True, key="chart_period",
        )
        st.caption("가격·이동평균·거래량만 보여줍니다 — 매수/매도 신호를 표시하지 않습니다.")
        fig = render_price_chart_figure(st.session_state.df, PERIOD_OPTIONS[period_label])
        st.plotly_chart(fig, use_container_width=True)

    with st.sidebar:
        st.caption(f"📊 {st.session_state.ticker} 상세 데이터는 아래 페이지에서 각각 볼 수 있습니다.")
        st.page_link("pages/1_섹터_Peer_비교.py", label="섹터 Peer 비교", icon="📊")
        st.page_link("pages/2_Peer_목록.py", label="Peer 목록", icon="📋")
        st.page_link("pages/3_소유구조.py", label="소유구조", icon="🏛️")
        st.page_link("pages/4_애널리스트_뉴스.py", label="애널리스트 관련 뉴스", icon="📰")
        st.page_link("pages/5_기업_이벤트_뉴스.py", label="기업 이벤트 뉴스", icon="🏢")

# ----------------------------------------------------------------------------
# STEP 1: 티커 입력 + 의도 선언
# ----------------------------------------------------------------------------
if st.session_state.step == 1:
    st.header("1. 티커 입력 & 포지션 의도 선언")
    raw_input = st.text_input(
        "티커 또는 기업명 (한글/영문 모두 가능, 예: USAR, Nvidia, 엔비디아)",
        value=st.session_state.get("ticker", ""),
    )
    intent = st.radio("포지션 의도", ["매수 검토", "매도 검토"], index=None, horizontal=True)

    if st.button("분석 시작 →", type="primary"):
        if not intent:
            st.error("포지션 의도(매수 검토/매도 검토)를 선택해주세요.")
            st.stop()
        with st.spinner(f"'{raw_input}' 티커 확인 중..."):
            ticker, matched_name = resolve_ticker(raw_input)
        if not ticker:
            st.error("티커 또는 기업명을 입력해주세요.")
            st.stop()
        if matched_name:
            st.info(f"'{raw_input}' → **{ticker}** ({matched_name})로 해석했습니다.")

        with st.spinner(f"{ticker} 데이터 수집 중... (가격, 지표, peer, 소유구조)"):
            try:
                df = get_price_history(ticker, "2024-01-01")
                if df is None or df.empty:
                    st.error("가격 데이터를 가져오지 못했습니다. 티커/기업명을 확인해주세요.")
                    st.stop()
                ind = compute_indicators(df)
                info = get_yf_info(ticker)
                earnings_date = get_yf_calendar(ticker)
                qqq_df = get_price_history("QQQ", "2023-01-01")
                qqq_ma200 = qqq_df["Close"].rolling(200).mean().iloc[-1]
                qqq_price = qqq_df["Close"].iloc[-1]
                regime_favorable = qqq_price > qqq_ma200

                peer_data = classify_peers(ticker)
                target_health = get_financial_health(ticker)
                ownership = get_ownership_summary(ticker)
                fund_ap = get_fund_level_active_passive(ticker)
                firm_holders = get_firm_level_holders(ticker)
                insider_tx = get_recent_insider_transactions(ticker)

                signals = classify_indicator_signals(ind)

                # 정성적 근거: 뉴스 톤(키워드 근사치) + 애널리스트 투자의견
                today_str = date.today().isoformat()
                from_str = (date.today() - timedelta(days=NEWS_LOOKBACK_DAYS)).isoformat()
                raw_news = get_finnhub_company_news(ticker, from_str, today_str)
                news_classified = classify_news_tone(raw_news)
                news_summary = news_tone_summary(news_classified)

                rec_trends = get_finnhub_recommendation_trends(ticker)
                analyst_trend = classify_analyst_trend(rec_trends)

                # 애널리스트/기업이벤트 관련 뉴스 — 더 넓은 기간에서 근사 필터링
                wide_from_str = (date.today() - timedelta(days=ANALYST_NEWS_LOOKBACK_DAYS)).isoformat()
                wide_news = get_finnhub_company_news(ticker, wide_from_str, today_str)
                analyst_news = filter_analyst_related_news(wide_news)
                corporate_events = filter_corporate_event_news(wide_news)
            except Exception as e:
                st.error(f"데이터 수집 중 오류: {e}")
                st.stop()

        # 새 종목 분석 시작 — 이전 종목의 메모·손절/익절가가 새 종목에 잘못 이어붙는 것을 방지
        st.session_state.pop("memo", None)
        st.session_state.pop("stop", None)
        st.session_state.pop("take_profit", None)

        st.session_state.update(
            ticker=ticker, intent=intent,
            df=df, ind=ind, info=info, earnings_date=earnings_date,
            qqq_price=qqq_price, qqq_ma200=qqq_ma200, regime_favorable=regime_favorable,
            peer_data=peer_data, target_health=target_health, ownership=ownership, fund_ap=fund_ap,
            firm_holders=firm_holders, insider_tx=insider_tx, signals=signals,
            news_classified=news_classified, news_summary=news_summary,
            analyst_trend=analyst_trend, analyst_news=analyst_news, corporate_events=corporate_events,
        )
        goto(2)

# ----------------------------------------------------------------------------
# STEP 2: 반대 관점 강제 노출 (원칙 A)
# ----------------------------------------------------------------------------
elif st.session_state.step == 2:
    intent = st.session_state.intent
    opposite_tag = "bearish" if intent == "매수 검토" else "bullish"
    st.header(f"2. ⚠️ 반대 관점부터 확인하세요 ({intent}에 대한 회의적 근거)")
    st.warning("이 단계를 건너뛸 수 없습니다. 아래 근거를 먼저 확인해야 다음 단계로 진행됩니다.")
    render_glossary(["RSI", "MACD", "이동평균(MA)", "볼린저밴드", "ATR"], title="ℹ️ 기술적 지표 설명")

    signals = st.session_state.signals
    opposite_signals = [s for s in signals if s[2] == opposite_tag]
    if not opposite_signals:
        st.info("기술적 지표상 뚜렷한 반대 근거는 없습니다. 다만 아래 리스크 항목은 확인하세요.")
    for name, desc, _ in opposite_signals:
        st.error(f"**{name}** — {desc}")

    # 이벤트 리스크 / 소유구조 기반 추가 회의적 근거
    st.subheader("추가 리스크 근거")
    earnings_date = st.session_state.earnings_date
    if earnings_date:
        days_left = int(np.busday_count(date.today(), earnings_date))
        if days_left <= 10:
            st.error(f"📅 실적 발표일이 {earnings_date} (D-{days_left})로 임박 — 변동성 급증 가능")
        else:
            st.caption(f"실적 발표일: {earnings_date} (D-{days_left}, 임박 아님)")

    if not st.session_state.regime_favorable:
        st.error(f"📉 시장 국면 비우호적 — QQQ({st.session_state.qqq_price:.2f}) < MA200({st.session_state.qqq_ma200:.2f})")

    ownership = st.session_state.ownership
    if ownership["float_ratio"] and ownership["float_ratio"] < 0.3:
        st.error(f"💧 저유동주식 — 유동주식비율 {ownership['float_ratio']*100:.1f}% (변동성 왜곡 위험)")
    if ownership["short_pct_float"] and ownership["short_pct_float"] > 0.1:
        st.error(f"🩳 공매도 비율 {ownership['short_pct_float']*100:.1f}% — 주목할 만한 수준")

    peer_stats = tier1_stats(st.session_state.peer_data["peers"])
    fwd_pe = st.session_state.info.get("forwardPE")
    if peer_stats and isinstance(fwd_pe, (int, float)) and fwd_pe > 0:
        multiple = fwd_pe / peer_stats["mean"]
        if multiple > 1.5:
            st.error(f"💰 포워드 PER {fwd_pe:.1f}가 동종 peer 평균({peer_stats['mean']:.1f}, n={peer_stats['n']})의 {multiple:.1f}배 — 고평가 논란")

    target_health = st.session_state.target_health
    if not target_health["fcf_positive"] and target_health["runway_months"] is not None \
            and target_health["runway_months"] < RUNWAY_RISK_MONTHS:
        st.error(f"⏳ 현금 런웨이 {target_health['runway_months']:.1f}개월 — 단기 증자/희석 가능성 (PER과 무관한 생존 리스크)")
    if isinstance(target_health["quick_ratio"], (int, float)) and target_health["quick_ratio"] < QUICK_RATIO_RISK:
        st.error(f"💧 당좌비율 {target_health['quick_ratio']:.2f} — 단기 채무 대비 현금성자산 크게 부족")

    st.subheader("정성적 근거 (뉴스·애널리스트)")
    st.caption("⚠️ 뉴스 톤은 키워드 매칭 기반 근사치입니다 (정밀 감성분석 아님, 원문 직접 확인 권장)")

    analyst_trend = st.session_state.analyst_trend
    if analyst_trend and analyst_trend["lean"] == opposite_tag:
        st.error(
            f"📊 애널리스트 의견({analyst_trend['period']}): 매수 {analyst_trend['strongBuy']+analyst_trend['buy']} / "
            f"중립 {analyst_trend['hold']} / 매도 {analyst_trend['strongSell']+analyst_trend['sell']} "
            f"— {'회의적' if opposite_tag=='bearish' else '긍정적'} 쪽으로 쏠림"
        )

    opposite_news = [n for n in st.session_state.news_classified if n["lean"] == opposite_tag]
    if opposite_news:
        for n in opposite_news[:5]:
            st.error(f"📰 {news_headline_link(n)} _({n['source']})_ — 매칭 키워드: {', '.join(n['matched'])}")
    else:
        st.caption(f"최근 {NEWS_LOOKBACK_DAYS}일 뉴스 중 반대 관점 키워드 매칭 없음")

    confirmed = st.checkbox("위 반대 관점 근거를 확인했습니다.")
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("← 처음으로"):
            goto(1)
    with col2:
        if st.button("다음: 지지 관점 확인 →", type="primary", disabled=not confirmed):
            goto(3)

# ----------------------------------------------------------------------------
# STEP 3: 지지 관점
# ----------------------------------------------------------------------------
elif st.session_state.step == 3:
    intent = st.session_state.intent
    same_tag = "bullish" if intent == "매수 검토" else "bearish"
    st.header(f"3. {intent}를 지지하는 근거")

    signals = st.session_state.signals
    same_signals = [s for s in signals if s[2] == same_tag]
    if not same_signals:
        st.info("기술적 지표상 뚜렷한 지지 근거는 없습니다.")
    for name, desc, _ in same_signals:
        st.success(f"**{name}** — {desc}")

    neutral_signals = [s for s in signals if s[2] == "neutral"]
    for name, desc, _ in neutral_signals:
        st.caption(f"(중립) {name} — {desc}")

    st.subheader("정성적 근거 (뉴스·애널리스트)")
    st.caption("⚠️ 뉴스 톤은 키워드 매칭 기반 근사치입니다 (정밀 감성분석 아님, 원문 직접 확인 권장)")

    analyst_trend = st.session_state.analyst_trend
    if analyst_trend and analyst_trend["lean"] == same_tag:
        st.success(
            f"📊 애널리스트 의견({analyst_trend['period']}): 매수 {analyst_trend['strongBuy']+analyst_trend['buy']} / "
            f"중립 {analyst_trend['hold']} / 매도 {analyst_trend['strongSell']+analyst_trend['sell']} "
            f"— {'긍정적' if same_tag=='bullish' else '회의적'} 쪽으로 쏠림"
        )
    elif analyst_trend:
        st.caption(
            f"애널리스트 의견({analyst_trend['period']}): 매수 {analyst_trend['strongBuy']+analyst_trend['buy']} / "
            f"중립 {analyst_trend['hold']} / 매도 {analyst_trend['strongSell']+analyst_trend['sell']} — 중립/혼조"
        )

    same_news = [n for n in st.session_state.news_classified if n["lean"] == same_tag]
    if same_news:
        for n in same_news[:5]:
            st.success(f"📰 {news_headline_link(n)} _({n['source']})_ — 매칭 키워드: {', '.join(n['matched'])}")
    else:
        st.caption(f"최근 {NEWS_LOOKBACK_DAYS}일 뉴스 중 지지 관점 키워드 매칭 없음")

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
    st.header("4. Conflict Board — 관점이 충돌하는 지점")
    st.caption("점수를 합산하지 않습니다. 서로 다른 카테고리가 다른 방향을 가리키는 지점만 나열합니다.")

    signals = st.session_state.signals
    tech_bullish = [f"[기술] {name}: {desc}" for name, desc, tag in signals if tag == "bullish"]
    tech_bearish = [f"[기술] {name}: {desc}" for name, desc, tag in signals if tag == "bearish"]

    analyst_trend = st.session_state.analyst_trend
    qual_bullish, qual_bearish = [], []
    if analyst_trend and analyst_trend["lean"] != "neutral":
        line = (f"[정성] 애널리스트 의견({analyst_trend['period']}): 매수 "
                f"{analyst_trend['strongBuy']+analyst_trend['buy']} / 매도 "
                f"{analyst_trend['strongSell']+analyst_trend['sell']}")
        (qual_bullish if analyst_trend["lean"] == "bullish" else qual_bearish).append(line)

    for n in st.session_state.news_classified:
        if n["lean"] == "bullish":
            qual_bullish.append(f"[정성] 뉴스: {news_headline_link(n)}")
        elif n["lean"] == "bearish":
            qual_bearish.append(f"[정성] 뉴스: {news_headline_link(n)}")

    bullish = tech_bullish + qual_bullish
    bearish = tech_bearish + qual_bearish

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🟢 긍정 방향")
        for line in bullish:
            st.write(f"- {line}")
        if not bullish:
            st.caption("없음")
    with col2:
        st.subheader("🔴 회의적 방향")
        for line in bearish:
            st.write(f"- {line}")
        if not bearish:
            st.caption("없음")

    if bullish and bearish:
        st.warning("⚠️ 기술적·정성적 근거 내에서도 방향이 엇갈립니다 — 아래 손절/익절에서 보수적으로 접근하는 것을 권장합니다.")
    st.caption("점수를 합산하지 않고 [기술]/[정성] 태그만 붙여 병치합니다 (원칙 B).")

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
    st.header("5. 손절가 / 익절가 (자동 산출)")

    ind = st.session_state.ind
    entry = ind["close"]
    st.metric("현재가 (진입가 가정)", f"${entry:.2f}")

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
            st.session_state.stop = stop
            st.session_state.take_profit = tp
            goto(6)

# ----------------------------------------------------------------------------
# STEP 6: 결정 이유 메모 (강제)
# ----------------------------------------------------------------------------
elif st.session_state.step == 6:
    st.header("6. 이 결정을 내린 이유")
    memo = st.text_area(
        "왜 지금 이 포지션을 검토하고 있나요? (한 줄 이상 필수)",
        value=st.session_state.get("memo", ""), height=120,
    )
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("← 이전 단계로"):
            goto(5)
    with col2:
        if st.button("다음: 최종 확인 →", type="primary", disabled=not memo.strip()):
            st.session_state.memo = memo.strip()
            goto(7)

# ----------------------------------------------------------------------------
# STEP 7: 최종 확인
# ----------------------------------------------------------------------------
elif st.session_state.step == 7:
    st.header("7. 최종 확인")
    st.write(f"**티커:** {st.session_state.ticker}  |  **의도:** {st.session_state.intent}")
    c1, c2 = st.columns(2)
    c1.metric("손절가", f"${st.session_state.stop:.2f}")
    c2.metric("보수적 익절가 (50%)", f"${st.session_state.take_profit:.2f}")
    st.write(f"**결정 이유 메모:** {st.session_state.memo}")
    st.info("나머지 50% 물량은 추격손절로 트레일링, 목표가 없음.")

    col1, col2, col3 = st.columns([1, 2, 2])
    with col1:
        if st.button("← 메모 수정"):
            goto(6)
    with col2:
        if st.button("✅ 그대로 진행 (기록)", type="primary"):
            append_entry({
                "ticker": st.session_state.ticker, "intent": st.session_state.intent,
                "entry_price": st.session_state.ind["close"], "stop": st.session_state.stop,
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
    st.header("8. ✅ 매매일지에 기록되었습니다")
    st.caption("실제 주문은 브로커에서 직접 실행하세요. 이 도구는 자동매매를 하지 않습니다.")
    st.dataframe(load_journal(), use_container_width=True)
    if st.button("새 종목 분석하기"):
        reset()

st.divider()
if st.button("🔄 처음부터 다시 (전체 초기화)"):
    reset()
