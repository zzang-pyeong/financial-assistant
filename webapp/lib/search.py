"""티커 검색 → 전체 데이터 수집 → session_state 저장. 시작화면과 사이드바 검색창이 공유."""

from datetime import date, timedelta

import streamlit as st

from lib.data import (
    get_price_history, get_yf_info, get_yf_calendar, get_finnhub_recommendation_trends,
    get_finnhub_company_news, resolve_ticker,
)
from lib.indicators import compute_indicators, classify_indicator_signals
from lib.peers import classify_peers, get_financial_health
from lib.ownership import (
    get_ownership_summary, get_fund_level_active_passive,
    get_recent_insider_transactions,
)
from lib.qualitative import (
    classify_news_tone, news_tone_summary, classify_analyst_trend,
    filter_analyst_related_news, filter_corporate_event_news,
)
from lib.config import NEWS_LOOKBACK_DAYS, ANALYST_NEWS_LOOKBACK_DAYS


def fetch_and_store_ticker(raw_input):
    """티커/기업명 문자열을 받아 전체 데이터를 수집해 session_state에 채운다.
    성공하면 True, 실패(에러 메시지 표시 후) 시 False를 반환."""
    with st.spinner(f"'{raw_input}' 티커 확인 중..."):
        ticker, matched_name = resolve_ticker(raw_input)
    if not ticker:
        st.error("티커 또는 기업명을 입력해주세요.")
        return False

    with st.spinner(f"{ticker} 데이터 수집 중..."):
        try:
            df = get_price_history(ticker, "2024-01-01")
            if df is None or df.empty:
                st.error("가격 데이터를 가져오지 못했습니다. 티커/기업명을 확인해주세요.")
                return False
            # MA60/60일 전고점 등 최대 60거래일 롤링 지표가 있어, 이보다 적으면
            # 지표가 NaN이 되어 손절/익절 계산이 깨짐 — 최근 상장 등으로 이력이
            # 짧은 종목은 여기서 미리 막고 안내한다.
            if len(df) < 60:
                st.error("가격 이력이 너무 짧아(최근 상장 등) 기술적 지표를 계산할 수 없습니다.")
                return False
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
            insider_tx = get_recent_insider_transactions(ticker)

            signals = classify_indicator_signals(ind)

            # 정성적 근거: 뉴스 톤(키워드 근사치) + 애널리스트 투자의견
            # 관련성 게이트를 위해 기업명 전달 — 종목과 무관한 기사를 걸러냄
            company_name = info.get("longName") or info.get("shortName") or ticker
            today_str = date.today().isoformat()
            from_str = (date.today() - timedelta(days=NEWS_LOOKBACK_DAYS)).isoformat()
            raw_news = get_finnhub_company_news(ticker, from_str, today_str)
            news_classified = classify_news_tone(raw_news, ticker, company_name)
            news_summary = news_tone_summary(news_classified)

            rec_trends = get_finnhub_recommendation_trends(ticker)
            analyst_trend = classify_analyst_trend(rec_trends)

            # 애널리스트/기업이벤트 관련 뉴스 — 더 넓은 기간에서 근사 필터링
            wide_from_str = (date.today() - timedelta(days=ANALYST_NEWS_LOOKBACK_DAYS)).isoformat()
            wide_news = get_finnhub_company_news(ticker, wide_from_str, today_str)
            analyst_news = filter_analyst_related_news(wide_news, ticker, company_name)
            corporate_events = filter_corporate_event_news(wide_news, ticker, company_name)
        except Exception as e:
            st.error(f"데이터 수집 중 오류: {e}")
            return False

    # 새 종목 검색 — 이전 종목의 포지션 의도·메모·손절/익절가가 새 종목에 잘못 이어붙는 것을 방지
    for k in ("intent", "memo", "stop", "take_profit", "entry_price"):
        st.session_state.pop(k, None)

    st.session_state.update(
        ticker=ticker,
        df=df, ind=ind, info=info, earnings_date=earnings_date,
        qqq_price=qqq_price, qqq_ma200=qqq_ma200, regime_favorable=regime_favorable,
        peer_data=peer_data, target_health=target_health, ownership=ownership, fund_ap=fund_ap,
        insider_tx=insider_tx, signals=signals,
        news_classified=news_classified, news_summary=news_summary,
        analyst_trend=analyst_trend, analyst_news=analyst_news, corporate_events=corporate_events,
    )
    if matched_name:
        st.toast(f"'{raw_input}' → {ticker} ({matched_name})")
    return True


def render_sidebar_search():
    """사이드바 어디서나 새 티커를 검색할 수 있는 작은 입력창. 시작화면과 동일한 메커니즘
    (Enter 제출, resolve_ticker → 전체 데이터 수집)을 그대로 재사용."""
    st.markdown(
        "<style>"
        "[data-testid='stSidebar'] [data-testid='stForm'] {"
        "  margin-bottom: 0.25rem;"
        "}"
        "</style>",
        unsafe_allow_html=True,
    )
    with st.form("sidebar_search_form", clear_on_submit=True, border=False):
        col_input, col_btn = st.columns([4, 1])
        with col_input:
            raw_input = st.text_input(
                "새 티커 검색", label_visibility="collapsed",
            )
        with col_btn:
            submitted = st.form_submit_button("→", use_container_width=True)

    if submitted and raw_input:
        if fetch_and_store_ticker(raw_input):
            st.session_state.step = "compare"
            st.switch_page("app.py")


# 사이드바 네비게이션 — 자동 네비(showSidebarNavigation=false)를 끈 대신 전 페이지에서 공통 사용
_SIDEBAR_PAGES = [
    ("pages/1_차트.py", "Price Chart", "📈"),
    ("pages/2_섹터_Peer_비교.py", "Peer Compare", "📊"),
    ("pages/3_Peer_목록.py", "Peer List", "📋"),
    ("pages/4_소유구조.py", "Ownership Map", "🏛️"),
    ("pages/5_애널리스트_뉴스.py", "Analyst News", "📰"),
    ("pages/6_기업_이벤트_뉴스.py", "Company Events", "🏢"),
    ("pages/7_옵션_데이터.py", "Options Data", "🧮"),
]


def render_sidebar_nav():
    """전체 상세 페이지로 이동하는 링크 목록."""
    for path, label, icon in _SIDEBAR_PAGES:
        st.page_link(path, label=label, icon=icon)


def render_sidebar():
    """검색창 + 전체 페이지 네비게이션 — app.py와 모든 서브페이지 사이드바에서 공통 사용."""
    render_sidebar_search()
    render_sidebar_nav()
