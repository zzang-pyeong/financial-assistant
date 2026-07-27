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
    get_ownership_summary,
)
from lib.qualitative import (
    classify_news_tone, news_tone_summary, classify_analyst_trend,
    filter_analyst_related_news, filter_corporate_event_news, match_counterparties,
)
from lib.config import NEWS_LOOKBACK_DAYS, ANALYST_NEWS_LOOKBACK_DAYS
from lib.known_companies import STATIC_KNOWN_COMPANIES

MAX_SEARCH_HISTORY = 30


def _remember_search(ticker, name):
    """검색 이력에 (ticker, name) 추가 — 관계도(마인드맵) 매칭용 '이미 아는 회사' 사전을
    peer 리스트 밖으로 넓히는 용도(예: 다른 산업의 공급망 파트너). 중복 티커는 재추가하지
    않고, 최근 MAX_SEARCH_HISTORY개만 보관. CSV 등으로 영속화하지 않음 — Streamlit Cloud는
    배포 프로세스를 여러 브라우저 세션이 공유하므로, 공유 파일에 쌓으면 다른 사용자의 검색
    이력이 내 관계도 매칭에 섞여 들어올 수 있어(session_state는 세션별로 격리되어 안전)."""
    history = st.session_state.get("search_history", [])
    if not any(h["ticker"].upper() == ticker.upper() for h in history):
        history.append({"ticker": ticker, "name": name})
        history = history[-MAX_SEARCH_HISTORY:]
    st.session_state.search_history = history


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

            signals = classify_indicator_signals(ind)

            # 정성적 근거: 뉴스 톤(키워드 근사치) + 애널리스트 투자의견
            # 관련성 게이트를 위해 기업명 전달 — 종목과 무관한 기사를 걸러냄
            company_name = info.get("longName") or info.get("shortName") or ticker
            today = date.today()
            today_str = today.isoformat()
            # 56일 뉴스 톤과 60일 상세 뉴스가 같은 API를 두 번 호출하던 것을 하나로 통합.
            wide_from_str = (today - timedelta(days=ANALYST_NEWS_LOOKBACK_DAYS)).isoformat()
            wide_news = get_finnhub_company_news(ticker, wide_from_str, today_str)
            recent_cutoff = (today - timedelta(days=NEWS_LOOKBACK_DAYS)).isoformat()
            recent_news = [n for n in wide_news if n.get("datetime") and
                           date.fromtimestamp(n["datetime"]).isoformat() >= recent_cutoff]
            news_classified = classify_news_tone(recent_news, ticker, company_name)
            news_summary = news_tone_summary(news_classified)

            rec_trends = get_finnhub_recommendation_trends(ticker)
            analyst_trend = classify_analyst_trend(rec_trends)

            # 애널리스트/기업이벤트 관련 뉴스도 위에서 받은 60일 데이터를 재사용.
            analyst_news = filter_analyst_related_news(wide_news, ticker, company_name)
            corporate_events = filter_corporate_event_news(wide_news, ticker, company_name)

            # 관계도(마인드맵) — "이미 아는 회사"만 상대방으로 인식: 정적 대형주 목록(최하위
            # 우선순위, 커버리지 확장용) < peer 리스트 < 세션 검색 이력(최우선, 가장 최신 확인).
            # peer만으론 경쟁사만 잡혀서 TSMC/MSFT/IREN 같은 실제 거래상대방을 놓치는 걸
            # 실증으로 확인해 정적 목록을 추가함(lib/known_companies.py 참조).
            _remember_search(ticker, company_name)
            known_companies = {kc["ticker"].upper(): kc for kc in STATIC_KNOWN_COMPANIES}
            for p in peer_data["peers"]:
                if p.get("name"):
                    known_companies[p["ticker"].upper()] = {"ticker": p["ticker"], "name": p["name"]}
            for h in st.session_state.search_history:
                known_companies[h["ticker"].upper()] = h
            relationship_edges = match_counterparties(
                corporate_events, list(known_companies.values()), exclude_ticker=ticker,
            )
        except Exception as e:
            st.error(f"데이터 수집 중 오류: {e}")
            return False

    # 새 종목 검색 — 이전 종목의 포지션 의도·메모·손절/익절가가 새 종목에 잘못 이어붙는 것을 방지
    for k in (
        "intent", "memo", "stop", "take_profit", "entry_price",
        "fund_ap", "insider_tx", "ownership_details_ticker",
    ):
        st.session_state.pop(k, None)

    st.session_state.update(
        ticker=ticker,
        df=df, ind=ind, info=info, earnings_date=earnings_date,
        qqq_price=qqq_price, qqq_ma200=qqq_ma200, regime_favorable=regime_favorable,
        peer_data=peer_data, target_health=target_health, ownership=ownership,
        signals=signals,
        news_classified=news_classified, news_summary=news_summary,
        analyst_trend=analyst_trend, analyst_news=analyst_news, corporate_events=corporate_events,
        relationship_edges=relationship_edges,
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
    ("pages/3_섹터_Peer_비교.py", "Peer Compare", "📊"),
    ("pages/4_소유구조.py", "Ownership Map", "🏛️"),
    ("pages/5_애널리스트_뉴스.py", "Analyst News", "📰"),
    ("pages/6_기업_이벤트_뉴스.py", "Company Events", "🏢"),
    ("pages/7_옵션_데이터.py", "Options Data", "🧮"),
    ("pages/8_관계도.py", "Relationship Map", "🕸️"),
]


def render_sidebar_nav():
    """전체 상세 페이지로 이동하는 링크 목록."""
    for path, label, icon in _SIDEBAR_PAGES:
        st.page_link(path, label=label, icon=icon)


def reset_session():
    """세션 상태 전체 초기화 후 검색 화면으로.
    서브페이지에서 호출될 때 st.rerun()만 쓰면 그 서브페이지 스크립트가 다시 실행되고,
    session_state가 비어있으니 require_analysis()가 "먼저 검색하세요" 중간 화면을
    보여준 뒤에야 다시 클릭해서 app.py로 가야 했음 — st.switch_page("app.py")로 바로
    이동시켜 한 번에 시작화면이 뜨게 한다."""
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.session_state.step = "search"
    st.switch_page("app.py")


def render_sidebar_reset():
    """검색창 바로 위, 눈에 띄지 않는 작은 글씨로 배치하는 세션 초기화 링크.
    페이지 네비게이션(st.page_link)과 다르게 테두리 없는 tertiary 버튼 + 톤다운된 회색으로
    존재감을 낮추고, hover 시에만 경고색(빨강)이 드러나게 해 '이동'이 아니라 '되돌릴 수
    없는 액션'임을 암시한다."""
    if st.session_state.get("step", "search") == "search":
        return
    with st.sidebar.container(key="reset_session_container"):
        if st.button("↺ 시작화면으로", key="reset_session_btn", type="tertiary"):
            reset_session()
    st.markdown(
        "<style>"
        "div.st-key-reset_session_container button {"
        "  color: #9096a2 !important; font-size: 0.8rem !important;"
        "  padding: 0 0 0.3rem 0 !important;"
        "}"
        "div.st-key-reset_session_container button:hover {"
        "  color: #e5484d !important;"
        "}"
        "</style>",
        unsafe_allow_html=True,
    )


def render_sidebar_price():
    """검색창 바로 위, 현재가 + 당일 변동을 작게 표시 — Conflict Board에서만 보이던
    가격 정보를 모든 화면에서 계속 보이게 함. fetch_and_store_ticker()가 이미
    받아온 info에서 꺼내 쓸 뿐 추가 API 호출은 없음."""
    info = st.session_state.get("info")
    if not info:
        return
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    if not isinstance(price, (int, float)):
        return
    change_pct = info.get("regularMarketChangePercent")
    change_str = ""
    if isinstance(change_pct, (int, float)):
        arrow = "▲" if change_pct >= 0 else "▼"
        change_str = f"  {arrow} {change_pct:+.2f}%"
    st.sidebar.caption(f"현재가 ${price:,.2f}{change_str}")


def render_sidebar():
    """세션 초기화 링크 + 현재가 + 검색창 + 전체 페이지 네비게이션 — app.py와 모든
    서브페이지 사이드바에서 공통 사용."""
    render_sidebar_reset()
    render_sidebar_price()
    render_sidebar_search()
    render_sidebar_nav()
