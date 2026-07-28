import re
import sys
from pathlib import Path
from datetime import datetime

import streamlit as st

sys.path.append(str(Path(__file__).parent))

from lib._shared_core.peers import format_pct
from lib._shared_core.page_helpers import (
    inject_base_styles, render_wordmark, render_ticker_header, render_info_cards,
)
from lib._shared_core.charts import render_market_cap_share_figure, STATIC_PLOTLY_CONFIG
from lib._shared_core.search import fetch_and_store_ticker, render_sidebar

_SENTENCE_BOUNDARY_RE = re.compile(r'(?<=[.!?])\s+(?=[A-Z"‘“])')
_MAX_DESC_CHARS = 220

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


def _money(v):
    """조 단위($1,000B) 이상은 T로 축약 — st.metric 등 한 줄 표시 공간에서 안 잘리게."""
    if not isinstance(v, (int, float)):
        return "N/A"
    if abs(v) >= 1e12:
        return f"${v/1e12:,.2f}T"
    return f"${v/1e9:,.2f}B"


def _find_ceo(officers):
    for o in officers or []:
        if "ceo" in (o.get("title") or "").lower():
            return o
    return None


def _first_sentence(text):
    """longBusinessSummary 전체(문단 여러 개, 수백~수천자)를 그대로 보여주면 예전에
    "회사소개창에서 사업설명 빼자"는 피드백을 받았던 그 문제(벽 같은 텍스트)가 재현된다
    — 대신 첫 문장 하나만 잘라 "무슨 일을 하는 회사인지" 짧게만 보여준다."""
    if not text:
        return None
    text = text.strip()
    m = _SENTENCE_BOUNDARY_RE.search(text)
    sentence = text[:m.start()] if m else text
    if len(sentence) > _MAX_DESC_CHARS:
        sentence = sentence[:_MAX_DESC_CHARS].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return sentence


def render_market_cap_share(ticker, info):
    """대상 종목이 동종업계(Peer Compare의 Tier1 판정과 동일한 기준)에서 시가총액 기준
    어느 정도 비중을 차지하는지 — "그 섹터에서 차지하고 있는 파이" 요청에 대한 답.
    ⚠️ 이건 업종 전체 매출 기준 "시장점유율"이 아니라, Finnhub이 제시한 peer 후보 중
    동일산업으로 판정된 것들(Tier1)만 모수로 한 시가총액 비중이다 — Peer Compare
    페이지가 쓰는 것과 완전히 같은 Tier1 집합이라 두 페이지 숫자가 어긋나지 않는다.
    Tier1이 비어있으면(예: AAPL처럼 동급 미국 상장사가 희소한 경우, 이전에 실측 확인)
    억지로 채우지 않고 그 사실 자체를 캡션으로 알린다."""
    target_cap = info.get("marketCap")
    peer_data = st.session_state.get("peer_data")
    tier1_peers = [
        p for p in (peer_data["peers"] if peer_data else [])
        if p["tier"] == 1 and isinstance(p.get("marketCap"), (int, float))
    ]
    if not isinstance(target_cap, (int, float)):
        return
    if not tier1_peers:
        st.caption("🥧 동종업계 시가총액 비중: 판정된 Tier1 peer 없음 — 비교 대상 부족")
        return

    st.plotly_chart(
        render_market_cap_share_figure(ticker, target_cap, tier1_peers),
        use_container_width=True, config=STATIC_PLOTLY_CONFIG,
    )
    total = target_cap + sum(p["marketCap"] for p in tier1_peers)
    share_pct = target_cap / total * 100
    sample_note = "" if len(tier1_peers) >= 3 else f" (n={len(tier1_peers)}, 표본 부족)"
    st.caption(
        f"🥧 동종업계(Tier1 peer {len(tier1_peers)}개) 시가총액 합계 대비 {ticker} 비중 "
        f"**{share_pct:.1f}%**{sample_note} — 업종 전체 매출 기준 시장점유율이 아니라 "
        "Peer Compare의 Tier1 판정 기준 시가총액 비중입니다."
    )


def render_company_intro(ticker, info):
    """검색 직후 첫 화면 — Conflict Board를 걷어내고 그 자리를 대신한다(2026-07-28).
    다 아는 회사(AAPL/NVDA 등)도 직원 수·배당정책·CEO 이름 같은 건 의외로 모르는 경우가
    많아서 넣었다. 회사 창업연도는 yfinance에 필드 자체가 없어 상장일
    (firstTradeDateMilliseconds)로 대체했고, CEO 취임/교체 시점도 데이터가 없어
    이름·직함만 표시한다(추측해서 채우지 않음)."""
    render_ticker_header(ticker)
    st.divider()

    sector = info.get("sector")
    industry = info.get("industry")
    sector_line = " · ".join(p for p in [sector, industry] if p)
    if sector_line:
        st.write(f"🏷️ {sector_line}")
    description = _first_sentence(info.get("longBusinessSummary"))
    if description:
        st.caption(description)

    employees = info.get("fullTimeEmployees")
    employees_str = f"{employees:,}명" if isinstance(employees, int) else "N/A"

    div_yield = info.get("dividendYield")  # 이 필드는 fraction이 아니라 값 그대로가 %(예: 0.32 = 0.32%)
    if isinstance(div_yield, (int, float)) and div_yield > 0:
        payout_str = format_pct(info.get("payoutRatio")) or "N/A"
        div_label, div_value, div_sub = "배당수익률", f"{div_yield:.2f}%", f"배당성향 {payout_str}"
    else:
        div_label, div_value, div_sub = "배당정책", "무배당", None

    first_trade_ms = info.get("firstTradeDateMilliseconds")
    listed = (
        datetime.utcfromtimestamp(first_trade_ms / 1000).strftime("%Y-%m-%d")
        if isinstance(first_trade_ms, (int, float)) else "N/A"
    )

    render_info_cards([
        ("시가총액", _money(info.get("marketCap"))),
        ("직원 수", employees_str),
        (div_label, div_value, div_sub),
        ("상장일", listed),
    ])

    render_market_cap_share(ticker, info)

    hq = ", ".join(p for p in [info.get("city"), info.get("state"), info.get("country")] if p)
    ceo = _find_ceo(info.get("companyOfficers"))
    ceo_str = f"**{ceo['name']}** ({ceo['title']})" if ceo else "**정보 없음**"
    st.write(f"🏢 본사: **{hq or 'N/A'}**&nbsp;&nbsp;&nbsp;&nbsp;👤 CEO: {ceo_str}")


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
        goto("intro")

# ----------------------------------------------------------------------------
# INTRO: 검색 직후 첫 화면 — 회사 기초 정보 (예전 Conflict Board 자리, 2026-07-28 교체)
# ----------------------------------------------------------------------------
elif st.session_state.step == "intro":
    render_company_intro(st.session_state.ticker, st.session_state.info)

