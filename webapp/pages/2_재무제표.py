import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.append(str(Path(__file__).parent.parent))

from lib._shared_core import data
from lib.page2_only_financials import financials
from lib._shared_core.charts import render_bar_chart_figure, STATIC_PLOTLY_CONFIG
from lib._shared_core.page_helpers import require_analysis, inject_base_styles, render_wordmark, render_ticker_header
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

st.caption(
    "⚠️ 아래 \"경영진 코멘트\"는 회사가 실적발표 8-K(또는 관련 보도)에서 실제로 밝힌 문장을 "
    "그대로 인용한 것입니다 — 모든 항목·모든 분기에 있는 것은 아니며, 없으면 억지로 채우지 "
    "않고 정직하게 비워둡니다."
)

income_stmt = data.get_yf_income_stmt(ticker)
cashflow = data.get_yf_cashflow(ticker)

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
latest = periods[0]


def _money(v):
    if not isinstance(v, (int, float)):
        return "N/A"
    return f"${v/1e9:,.2f}B"


def _pct(v):
    if not isinstance(v, (int, float)):
        return "N/A"
    return f"{v*100:.1f}%"


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


# --- 핵심 지표 카드 (최근 회계연도 기준) --------------------------------------------
st.subheader(f"핵심 지표 ({latest.strftime('%Y-%m-%d')} 기준 회계연도)")
row1 = st.columns(4)
row1[0].metric("매출", _money(revenue.get(latest)))
row1[1].metric("매출총이익률", _pct((gross_margin or {}).get(latest)))
row1[2].metric("영업이익률", _pct((operating_margin or {}).get(latest)))
row1[3].metric("순이익", _money((net_income or {}).get(latest)))

row2 = st.columns(4)
row2[0].metric("CapEx", _money((capex or {}).get(latest)))
row2[1].metric("영업현금흐름(OCF)", _money((ocf or {}).get(latest)))
row2[2].metric("잉여현금흐름(FCF)", _money((fcf or {}).get(latest)))
row2[3].metric("CapEx / 매출", _pct((capex_pct or {}).get(latest)))

# --- 추이 -----------------------------------------------------------------------
st.subheader("추이")
chart_cols = st.columns(2)
with chart_cols[0]:
    revenue_scaled, revenue_unit = _auto_unit(pd.Series(revenue).sort_index())
    st.caption(f"매출 (단위: ${revenue_unit})" if revenue_unit else "매출 (단위: $)")
    st.plotly_chart(
        render_bar_chart_figure(revenue_scaled),
        use_container_width=True, config=STATIC_PLOTLY_CONFIG,
    )
with chart_cols[1]:
    if capex:
        capex_scaled, capex_unit = _auto_unit(pd.Series(capex).sort_index())
        st.caption(f"CapEx (단위: ${capex_unit})" if capex_unit else "CapEx (단위: $)")
        st.plotly_chart(
            render_bar_chart_figure(capex_scaled),
            use_container_width=True, config=STATIC_PLOTLY_CONFIG,
        )
    else:
        st.caption("CapEx 데이터 없음 (자산경량 업종에 흔함)")

st.divider()

# --- 경영진 코멘트 ------------------------------------------------------------------
# 비용 제한: 가장 최근 회계기간에 대해서만, 핵심 항목 4개만 조회한다(전체 기간·전체
# 항목을 다 훑으면 8-K 첨부문서를 항목 수만큼 반복 스캔해야 해서 페이지가 느려진다).
_COMMENTARY_METRICS = [
    ("revenue", "매출"),
    ("gross_margin", "매출총이익률"),
    ("operating_margin", "영업이익률·영업비용"),
    ("capex", "CapEx"),
]

st.subheader(f"경영진 코멘트 ({latest.strftime('%Y-%m-%d')} 기준 회계연도)")
company_name = (st.session_state.info or {}).get("shortName") or ticker
latest_date = latest.date()

with st.spinner("실적발표 공시·뉴스에서 경영진 코멘트를 찾는 중..."):
    for metric_key, label in _COMMENTARY_METRICS:
        quotes = financials.find_commentary(ticker, company_name, metric_key, latest_date)
        with st.expander(label, expanded=bool(quotes)):
            if not quotes:
                st.caption("공개된 설명 없음")
                continue
            for q in quotes:
                st.markdown(f"> {q['quote']}")
                st.caption(f"{q['source_kind']} · {q['date']} · [원문]({q['url']})")
