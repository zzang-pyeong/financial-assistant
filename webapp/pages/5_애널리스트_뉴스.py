import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.append(str(Path(__file__).parent.parent))

from lib._shared_core.translate import to_korean, prefetch_korean
from lib._shared_core.config import ANALYST_NEWS_LOOKBACK_DAYS, ANALYST_NEWS_DISPLAY_LIMIT
from lib._shared_core.page_helpers import (
    require_analysis, news_date_str, inject_base_styles, render_wordmark, render_ticker_header,
)
from lib._shared_core.search import render_sidebar

st.set_page_config(page_title="Analyst News — EnterTicker", layout="wide")
inject_base_styles()
require_analysis()

with st.sidebar:
    render_sidebar()

ticker = st.session_state.ticker
with st.container(key="page_header"):
    render_wordmark("Analyst", "News", align="center")
    render_ticker_header(ticker)
st.divider()

# --- 애널리스트 투자의견 분포 (예전 Conflict Board 정성적 근거, 2026-07-28 이전) --------------
analyst_trend = st.session_state.get("analyst_trend")
if analyst_trend:
    st.subheader("애널리스트 투자의견 분포")
    cols = st.columns(4)
    cols[0].metric("매수", analyst_trend["strongBuy"] + analyst_trend["buy"])
    cols[1].metric("보유", analyst_trend["hold"])
    cols[2].metric("매도", analyst_trend["strongSell"] + analyst_trend["sell"])
    cols[3].metric("기준 시점", analyst_trend["period"] or "—")
    st.divider()

def _date_str(epoch):
    if not epoch:
        return ""
    try:
        return datetime.fromtimestamp(epoch).strftime("%Y-%m-%d")
    except Exception:
        return ""


def _price_target_change(a):
    """이전 → 신규 목표주가 전환을 "$X → $Y (+Z%)" 형태로. 이전 목표주가가 없으면
    (신규 커버리지 등) 신규 목표주가만, 그마저 없으면 빈 칸."""
    current = a.get("price_target")
    prior = a.get("prior_price_target")
    if current is None:
        return ""
    if prior is None or prior == current:
        return f"${current:.2f}"
    pct = (current / prior - 1) * 100
    return f"${prior:.2f} → ${current:.2f} ({pct:+.1f}%)"


def _price_at(df, epoch):
    """df(일봉 가격 이력)에서 epoch 시점 또는 그 직전 마지막 거래일 종가를 찾는다.
    df가 2024-01-01부터라(lib/search.py) 그보다 오래된 등급 변경은 못 찾아 None —
    값을 지어내지 않고 빈 칸으로 둔다."""
    if not epoch or df is None or df.empty:
        return None
    try:
        ts = pd.Timestamp(datetime.fromtimestamp(epoch).date())
        pos = df.index.asof(ts)
        if pd.isna(pos):
            return None
        return float(df.loc[pos, "Close"])
    except Exception:
        return None


# --- 목표주가 --------------------------------------------------------------
price_target = st.session_state.get("price_target")
if price_target:
    info = st.session_state.info
    current_price = info.get("currentPrice") or info.get("regularMarketPrice")
    st.subheader("목표주가")
    cols = st.columns(4)
    cols[0].metric("평균", f"${price_target['mean']:.2f}" if price_target.get("mean") is not None else "—")
    cols[1].metric("최고", f"${price_target['high']:.2f}" if price_target.get("high") is not None else "—")
    cols[2].metric("최저", f"${price_target['low']:.2f}" if price_target.get("low") is not None else "—")
    if current_price and price_target.get("mean"):
        upside = (price_target["mean"] / current_price - 1) * 100
        cols[3].metric("현재가 대비", f"{upside:+.1f}%", help=f"현재가 ${current_price:.2f} 기준")
    else:
        cols[3].metric("현재가 대비", "—")
    st.caption(f"⚠️ 애널리스트 목표주가는 예측일 뿐 확정된 가격이 아닙니다 — 출처: {price_target['source']}.")
    st.divider()

# --- 최근 상향/하향 이력 -----------------------------------------------------
analyst_actions = st.session_state.get("analyst_actions", [])
if analyst_actions:
    price_df = st.session_state.get("df")
    st.subheader("최근 1년 상향/하향 이력")
    st.dataframe(
        pd.DataFrame([{
            "날짜": _date_str(a["date"]),
            "증권사": a["firm"] or "",
            "증권사 규모": a["broker_tier"],
            "변경": a["action_label"],
            "등급": (f"{a['from_grade']} → {a['to_grade']}" if a["from_grade"] else a["to_grade"]),
            "당시 주가": (
                f"${p:.2f}" if (p := _price_at(price_df, a["date"])) is not None else ""
            ),
            "목표주가 변경": _price_target_change(a),
        } for a in analyst_actions]),
        hide_index=True, use_container_width=True, height=420,
    )
    st.caption(
        f"최근 1년 내 전체 {len(analyst_actions)}건. 출처: {analyst_actions[0]['source']}. "
        "⚠️ '증권사 규모'는 이름 인지도 기준 근사치일 뿐 실제 리서치 적중률·트랙레코드가 "
        "아닙니다 — 대형 IB라고 항상 더 정확한 것은 아닙니다. '목표주가 변경'은 Finnhub "
        "소스에서는 제공되지 않아 비어있을 수 있습니다."
    )
    st.divider()

st.caption(
    f"최근 {ANALYST_NEWS_LOOKBACK_DAYS}일 뉴스 중 'upgrade/price target' 등 키워드가 있는 것만 필터링. "
    "⚠️ 실제 매수/매도 집계의 확정된 근거는 아니며, 관련 있어 보이는 뉴스일 뿐입니다."
)
analyst_news = st.session_state.get("analyst_news", [])
if analyst_news:
    shown = analyst_news[:ANALYST_NEWS_DISPLAY_LIMIT]
    # 표시할 헤드라인을 먼저 한꺼번에 병렬 번역해둔다 — 안 그러면 아래 루프가 헤드라인마다
    # 순차 HTTP 요청을 보내 화면이 한 줄씩 늦게 그려진다(Conflict Board와 같은 문제).
    with st.spinner("헤드라인 번역 중..."):
        prefetch_korean([n["headline"] for n in shown])
    for n in shown:
        headline = to_korean(n["headline"])
        title = f"[{headline}]({n['url']})" if n.get("url") else headline
        date_str = news_date_str(n)
        date_part = f" ({date_str})" if date_str else ""
        st.write(f"- {title}{date_part}")
        st.caption(f"매칭 키워드: {', '.join(n['matched'])} _({n.get('source', '')})_")
else:
    st.caption("해당 기간 내 애널리스트 관련 뉴스 없음")
