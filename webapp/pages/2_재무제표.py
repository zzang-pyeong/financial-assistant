import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

sys.path.append(str(Path(__file__).parent.parent))

from lib._shared_core import data
from lib.page2_only_financials import financials
from lib._shared_core.charts import render_bar_chart_figure, STATIC_PLOTLY_CONFIG
from lib._shared_core.page_helpers import (
    require_analysis, inject_base_styles, render_wordmark, render_ticker_header, render_info_cards,
)
from lib._shared_core.search import render_sidebar

st.set_page_config(page_title="Financial Statements — EnterTicker", layout="wide")
inject_base_styles()
require_analysis()

with st.sidebar:
    render_sidebar()

ticker = st.session_state.ticker
with st.container(key="page_header"):
    render_wordmark("Financial", "Statements", align="center")
    render_ticker_header(ticker)
st.divider()

# 실적 임박 경고 (예전 Conflict Board 방향-무관 참고사항, 2026-07-28 이전) — 실제로 급할
# 때(영업일 기준 10일 이내)만 노출, 평소엔 생략.
earnings_date = st.session_state.get("earnings_date")
if earnings_date:
    days_left = int(np.busday_count(date.today(), earnings_date))
    if 0 <= days_left <= 10:
        st.caption(f"📅 실적 발표일이 {earnings_date} (D-{days_left})로 임박 — 변동성 급증 가능")

st.caption(
    "⚠️ 아래 \"경영진 코멘트\"는 회사가 실적발표 8-K(또는 관련 보도)에서 실제로 밝힌 문장을 "
    "그대로 인용한 것입니다 — 모든 항목·모든 분기에 있는 것은 아니며, 없으면 억지로 채우지 "
    "않고 정직하게 비워둡니다."
)

# --- 보기 단위(분기/연간) 선택 ------------------------------------------------------
# 기본값은 분기(사용자 피드백, 2026-07-28: 연간만 보여주면 최근 실적 흐름을 놓친다).
view_mode = st.segmented_control(
    "보기 단위", ["분기", "연간"], default="분기", key="fin_view_mode",
)
is_quarterly = view_mode != "연간"

income_stmt = data.get_yf_income_stmt(ticker, quarterly=is_quarterly)
cashflow = data.get_yf_cashflow(ticker, quarterly=is_quarterly)

if income_stmt is None or income_stmt.empty:
    st.warning("재무제표 데이터를 가져오지 못했습니다.")
    st.stop()

revenue = financials.revenue_series(income_stmt)
gross_margin = financials.gross_margin_series(income_stmt)
operating_margin = financials.operating_margin_series(income_stmt)
net_income = financials.net_income_series(income_stmt)
capex = financials.capex_series(cashflow)
ocf = financials.operating_cash_flow_series(cashflow)
fcf = financials.free_cash_flow_series(cashflow)
capex_pct = financials.capex_pct_revenue(capex, revenue)

if not revenue:
    st.warning("매출 데이터를 가져오지 못했습니다.")
    st.stop()

periods = sorted(revenue.keys(), reverse=True)


def _money(v):
    if not isinstance(v, (int, float)):
        return "N/A"
    if abs(v) >= 1e12:
        return f"${v/1e12:,.2f}T"
    return f"${v/1e9:,.2f}B"


def _pct(v):
    if not isinstance(v, (int, float)):
        return "N/A"
    return f"{v*100:.1f}%"


def _period_label(p):
    if is_quarterly:
        return f"{p.year} Q{(p.month - 1) // 3 + 1}"
    return f"FY{p.year}"


def _delta_money_pct(curr, prev):
    """전 기간 대비 증감률(%) — 둘 다 유효한 숫자일 때만, 지어내지 않는다."""
    if not isinstance(curr, (int, float)) or not isinstance(prev, (int, float)) or prev == 0:
        return None
    return f"{(curr - prev) / abs(prev) * 100:+.1f}%"


def _delta_pp(curr, prev):
    """마진류(비율) 지표는 %가 아니라 %p(퍼센트포인트) 차이로 보여준다."""
    if not isinstance(curr, (int, float)) or not isinstance(prev, (int, float)):
        return None
    return f"{(curr - prev) * 100:+.1f}%p"


def _auto_unit(series):
    """차트 y축이 전체 자릿수(예: 220,000,000,000)를 그대로 표시하면 라벨이 길어서
    잘려 보인다(실사용 스크린샷으로 확인) — 시리즈 최대값 크기에 맞는 단위(B/M/K)로
    스케일링해서 축에는 짧은 숫자만 나오게 하고, 단위는 캡션에 별도 표시한다."""
    max_abs = series.abs().max()
    if max_abs >= 1e9:
        return series / 1e9, "B"
    if max_abs >= 1e6:
        return series / 1e6, "M"
    if max_abs >= 1e3:
        return series / 1e3, "K"
    return series, ""


# --- 조회 기간 선택 (기본: 최신) ----------------------------------------------------
period_idx = st.selectbox(
    "조회 기간", options=range(len(periods)),
    format_func=lambda i: f"{_period_label(periods[i])} ({periods[i].strftime('%Y-%m-%d')} 마감)",
    index=0,
)
selected = periods[period_idx]
prev_period = periods[period_idx + 1] if period_idx + 1 < len(periods) else None
delta_note = "전분기 대비" if is_quarterly else "전년 대비"

# --- 핵심 지표 카드 -----------------------------------------------------------------
st.subheader(f"핵심 지표 — {_period_label(selected)} ({selected.strftime('%Y-%m-%d')} 마감)")
st.caption(f"증감률은 {delta_note} · 색상 없이 방향·크기만 표시합니다(가치 판단 아님)")

with st.container(border=True):
    st.caption("📈 손익")
    render_info_cards([
        (
            "매출", _money(revenue.get(selected)), None,
            _delta_money_pct(revenue.get(selected), (revenue or {}).get(prev_period)) if prev_period else None,
        ),
        (
            "매출총이익률", _pct((gross_margin or {}).get(selected)), None,
            _delta_pp((gross_margin or {}).get(selected), (gross_margin or {}).get(prev_period)) if prev_period else None,
        ),
        (
            "영업이익률", _pct((operating_margin or {}).get(selected)), None,
            _delta_pp((operating_margin or {}).get(selected), (operating_margin or {}).get(prev_period)) if prev_period else None,
        ),
        (
            "순이익", _money((net_income or {}).get(selected)), None,
            _delta_money_pct((net_income or {}).get(selected), (net_income or {}).get(prev_period)) if prev_period else None,
        ),
    ])

with st.container(border=True):
    st.caption("💰 현금흐름")
    render_info_cards([
        (
            "CapEx", _money((capex or {}).get(selected)), None,
            _delta_money_pct((capex or {}).get(selected), (capex or {}).get(prev_period)) if prev_period else None,
        ),
        (
            "영업현금흐름(OCF)", _money((ocf or {}).get(selected)), None,
            _delta_money_pct((ocf or {}).get(selected), (ocf or {}).get(prev_period)) if prev_period else None,
        ),
        (
            "잉여현금흐름(FCF)", _money((fcf or {}).get(selected)), None,
            _delta_money_pct((fcf or {}).get(selected), (fcf or {}).get(prev_period)) if prev_period else None,
        ),
        (
            "CapEx / 매출", _pct((capex_pct or {}).get(selected)), None,
            _delta_pp((capex_pct or {}).get(selected), (capex_pct or {}).get(prev_period)) if prev_period else None,
        ),
    ])

# --- 추이 -----------------------------------------------------------------------
st.subheader(f"추이 ({'분기별' if is_quarterly else '연도별'})")
chart_cols = st.columns(2)
with chart_cols[0]:
    revenue_scaled, revenue_unit = _auto_unit(pd.Series(revenue).sort_index())
    st.caption(f"매출 (단위: ${revenue_unit})" if revenue_unit else "매출 (단위: $)")
    st.plotly_chart(
        render_bar_chart_figure(revenue_scaled, quarterly=is_quarterly),
        use_container_width=True, config=STATIC_PLOTLY_CONFIG,
    )
with chart_cols[1]:
    if capex:
        capex_scaled, capex_unit = _auto_unit(pd.Series(capex).sort_index())
        st.caption(f"CapEx (단위: ${capex_unit})" if capex_unit else "CapEx (단위: $)")
        st.plotly_chart(
            render_bar_chart_figure(capex_scaled, quarterly=is_quarterly),
            use_container_width=True, config=STATIC_PLOTLY_CONFIG,
        )
    else:
        st.caption("CapEx 데이터 없음 (자산경량 업종에 흔함)")

st.divider()

# --- 경영진 코멘트 ------------------------------------------------------------------
# 비용 제한: 선택된 기간에 대해서만, 핵심 항목 4개만 조회한다(전체 기간·전체
# 항목을 다 훑으면 8-K 첨부문서를 항목 수만큼 반복 스캔해야 해서 페이지가 느려진다).
_COMMENTARY_METRICS = [
    ("revenue", "매출"),
    ("gross_margin", "매출총이익률"),
    ("operating_margin", "영업이익률·영업비용"),
    ("capex", "CapEx"),
]

st.subheader(f"경영진 코멘트 — {_period_label(selected)} ({selected.strftime('%Y-%m-%d')} 마감)")
company_name = (st.session_state.info or {}).get("shortName") or ticker
selected_date = selected.date()

with st.spinner("실적발표 공시·뉴스에서 경영진 코멘트를 찾는 중..."):
    for metric_key, label in _COMMENTARY_METRICS:
        quotes = financials.find_commentary(ticker, company_name, metric_key, selected_date)
        with st.expander(label, expanded=bool(quotes)):
            if not quotes:
                st.caption("공개된 설명 없음")
                continue
            for q in quotes:
                st.markdown(f"> {q['quote']}")
                st.caption(f"{q['source_kind']} · {q['date']} · [원문]({q['url']})")
