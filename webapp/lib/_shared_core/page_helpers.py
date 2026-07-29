from datetime import datetime

import streamlit as st

from .data import get_company_logo_url


def inject_base_styles():
    """앱 전체 글꼴을 각진 느낌의 산세리프(IBM Plex Sans KR)로 통일하고,
    기본 스피너 아이콘을 데이터 수집 컨셉에 맞는 회전 이모지로 교체."""
    st.markdown(
        "<style>"
        "@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600;700&display=swap');"
        "html, body, .stApp, .stApp * { font-family: 'IBM Plex Sans KR', sans-serif !important; }"
        "[data-testid='stIconMaterial'], [data-testid='stIconMaterial'] * {"
        "  font-family: 'Material Symbols Rounded' !important;"
        "}"
        "@keyframes spin-emoji { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }"
        "[data-testid='stSpinnerIcon'] {"
        "  background: none !important; border: none !important;"
        "  width: 1.3em !important; height: 1.3em !important;"
        "  display: inline-flex !important; align-items: center; justify-content: center;"
        "}"
        "[data-testid='stSpinnerIcon']::before {"
        "  content: '\\1F310'; display: inline-block; font-size: 1.15rem;"
        "  animation: spin-emoji 1.1s linear infinite;"
        "}"
        "div.st-key-page_header { text-align: center; }"
        "div.st-key-page_header [data-testid='stCaptionContainer'] { justify-content: center; }"
        "div.st-key-page_header [data-testid='stPageLink'] { justify-content: center; }"
        "</style>",
        unsafe_allow_html=True,
    )


def render_wordmark(first, second, size="2.2rem", align="left", margin="0 0 1rem 0", sep=" "):
    """EnterTicker/Conflict Point와 같은 타이포그래피 스타일의 2단어 워드마크.
    두 번째 단어만 브랜드 블루로 강조. sep="" 이면 EnterTicker처럼 붙여 쓴다."""
    st.markdown(
        f"<div style='text-align:{align}; margin:{margin}; font-size:{size}; "
        f"font-weight:700; letter-spacing:-0.02em;'>"
        f"{first}{sep}<span style='color:#2f6fed;'>{second}</span></div>",
        unsafe_allow_html=True,
    )


def render_ticker_header(ticker, suffix=None):
    """페이지 헤더의 티커 표시 — 굵고 진한 글씨 + 정사각형 회사 로고를 나란히 보여준다
    (사용자 피드백: 기존 st.caption(ticker)은 옅은 회색이라 눈에 잘 안 띔). suffix가
    있으면 " · {suffix}"를 이어붙인다(예: 관계도의 "기업 연결 근거").
    로고는 object-fit:contain으로 정사각 틀에 맞춰서 넣는다 — 관계도 그래프 노드의 원형
    크롭(lib/logos.py)과 달리 여기는 일반 HTML이라 서버 가공 없이 CSS만으로 충분하다.
    로고가 없는 종목(소형주 등)은 텍스트만 — 로고 없음은 흔한 정상 경로."""
    logo_url = get_company_logo_url(ticker)
    logo_html = (
        f"<img src='{logo_url}' style='width:28px; height:28px; object-fit:contain; "
        "border-radius:6px; border:1px solid #e5e7eb; padding:2px; background:#fff;' />"
        if logo_url else ""
    )
    suffix_html = (
        f"<span style='color:#6b7280; font-weight:400;'> · {suffix}</span>" if suffix else ""
    )
    st.markdown(
        "<div style='display:flex; align-items:center; justify-content:center; "
        f"gap:0.45rem; font-size:1.05rem;'>{logo_html}"
        f"<span style='font-weight:700; color:#111827;'>{ticker}</span>{suffix_html}</div>",
        unsafe_allow_html=True,
    )


def render_info_cards(cards):
    """label/value(/sub/delta) 카드 그리드. st.metric은 값이 조금만 길어도 말줄임표로
    잘라버려서(실측: TSLA 시가총액 "$1,193.6...", 날짜 "2026-07-...") 대신 직접 HTML로
    그린다 — flex-wrap이라 좁은 화면에선 자동 줄바꿈되고, 값도 word-break로 감싸 잘리지
    않는다. cards: [(label, value), (label, value, sub), (label, value, sub, delta), ...].
    delta는 이 앱 규칙(색상으로 유불리 암시 안 함)에 맞춰 색 없이 +/- 기호로만 방향 표시."""
    def _card(item):
        label, value = item[0], item[1]
        sub = item[2] if len(item) > 2 else None
        delta = item[3] if len(item) > 3 else None
        sub_html = (
            f"<div style='font-size:0.75rem; color:#9ca3af; margin-top:0.25rem;'>{sub}</div>"
            if sub else ""
        )
        delta_html = (
            f"<div style='font-size:0.85rem; color:#4b5563; margin-top:0.3rem;'>{delta}</div>"
            if delta else ""
        )
        return (
            "<div style='flex:1 1 150px; min-width:150px; padding:0.9rem 1.1rem; "
            "border:1px solid #e5e7eb; border-radius:12px; background:#fafbfc;'>"
            f"<div style='font-size:0.8rem; color:#6b7280; margin-bottom:0.35rem; "
            f"word-break:break-word;'>{label}</div>"
            f"<div style='font-size:1.4rem; font-weight:700; color:#111827; line-height:1.25; "
            f"word-break:break-word;'>{value}</div>{sub_html}{delta_html}</div>"
        )

    html = "".join(_card(c) for c in cards)
    st.markdown(
        f"<div style='display:flex; flex-wrap:wrap; gap:0.9rem; margin:0.6rem 0 1.2rem 0;'>{html}</div>",
        unsafe_allow_html=True,
    )


def require_analysis():
    """상세 데이터 하위 페이지: 아직 조회 전이면 메인 페이지로 안내하고 중단.
    여기를 통과했다는 건 사이드바 페이지 링크(또는 미니 검색창·관계도 노드 클릭)로 실제
    이동했다는 뜻이라, 사이드바 발견성 화살표(render_sidebar_discovery_arrow)를 다시 안
    보이게 하는 "완료" 표시를 이 한 곳에서만 남긴다 — 8개 서브페이지 각각에 따로 심지
    않아도 전부 커버된다."""
    if "peer_data" not in st.session_state:
        st.info("Search a ticker on the main page first.")
        st.page_link("app.py", label="← Back to Search", icon="🏠")
        st.stop()
    st.session_state["sidebar_discovery_completed"] = True


def render_sidebar_discovery_arrow():
    """검색 직후 첫 분석 홈 화면에서만, 사이드바 메뉴 영역을 가리키는 1회성 펄스 화살표를
    보여준다 — 사이드바는 그대로 두고(본문에 메뉴 반복 배치 안 함), 처음 온 사용자가
    "왼쪽에 메뉴가 있다"는 것만 한 번 학습하게 하는 용도. 문구·말풍선·모달은 안 붙인다
    (원칙: 상시 도움말 없음). 특정 메뉴를 가리키지 않고 메뉴 영역 전체를 가리킨다.

    세션 안에서 최초 1회만 렌더링한다 — require_analysis()가 사이드바 페이지 이동을
    감지하면 sidebar_discovery_completed를 세우고, 그게 없어도 이 함수가 한 번
    렌더되는 순간 sidebar_discovery_shown을 세워서(아직 메뉴를 안 눌렀어도) 같은 방문
    중 홈 화면이 다른 이유로 다시 그려질 때 애니메이션이 처음부터 재생되는 걸 막는다.

    ⚠️ localStorage 없이 st.session_state만 쓴다 — 새로고침하면 다시 보일 수 있지만,
    이 프로젝트는 세션 간 영속화를 의도적으로 안 하는 선례가 이미 있고(search_history),
    이 기능도 "첫인상 발견성" 목적상 새로고침 후 한 번 더 보이는 정도는 치명적이지
    않다고 판단해 새 의존성(streamlit-javascript 등) 추가 없이 이 범위로 한정했다."""
    if st.session_state.get("sidebar_discovery_completed"):
        return
    if st.session_state.get("sidebar_discovery_shown"):
        return
    st.session_state["sidebar_discovery_shown"] = True

    # 실제 렌더링을 좌표로 재서 맞췄다(기본 폭 사이드바 기준): 사이드바 오른쪽 끝이
    # x=300px, 본문 컬럼이 x=380px부터 시작해서 그 사이 80px는 원래 빈 여백이라 뭘
    # 놓아도 사이드바·본문 어느 쪽과도 안 겹친다. 세로는 메뉴 링크 목록이 시작하는
    # y=248px에 맞춰서, "↖"가 메뉴 목록 시작점을 짚고 위쪽(사이드바 전체)을 가리키게
    # 했다. ⚠️ 사이드바를 사용자가 리사이즈했거나 뷰포트가 많이 다르면 어긋날 수 있음
    # (반응형 접힘은 이번 범위에서 고려 안 함, 데스크톱 기준 근사치).
    st.markdown(
        "<style>"
        "@keyframes sidebar-discovery-pulse {"
        "  0%, 100% { opacity: 0.72; transform: translate(0, 0) scale(1); }"
        "  50% { opacity: 1; transform: translate(-6px, -4px) scale(1.08); }"
        "}"
        "@keyframes sidebar-discovery-fadeout {"
        "  from { opacity: 1; } to { opacity: 0; visibility: hidden; }"
        "}"
        ".sidebar-discovery-arrow {"
        "  position: fixed; top: 250px; left: 316px; z-index: 999;"
        "  font-size: 2rem; font-weight: 700; line-height: 1;"
        "  color: #2f6fed; pointer-events: none;"
        "  animation: sidebar-discovery-pulse 1.15s ease-in-out 4,"
        "             sidebar-discovery-fadeout 0.4s ease-in 4.6s 1 forwards;"
        "}"
        "@media (prefers-reduced-motion: reduce) {"
        "  .sidebar-discovery-arrow { animation: none; opacity: 0.85; }"
        "}"
        "</style>"
        "<div class='sidebar-discovery-arrow'>↖</div>",
        unsafe_allow_html=True,
    )


def news_date_str(n):
    """Finnhub unix timestamp를 날짜로 변환 — 뉴스 신선도 표시용."""
    ts = n.get("datetime")
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    except (ValueError, OSError):
        return None
