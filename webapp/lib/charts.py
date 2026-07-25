"""최근 주가 캔들차트. 판단을 대신하지 않도록 매수/매도 신호 표시 없이
가격·이동평균·거래량만 병치해서 보여준다 (원칙 B)."""

import math

import plotly.graph_objects as go
from plotly.subplots import make_subplots

PERIOD_OPTIONS = {"1개월": 21, "3개월": 63, "6개월": 126, "1년": 252, "전체": None}

# Yahoo Finance 분봉 제약: interval별 조회 가능한 최대 기간이 다름 (1m→7일, 5m/15m/30m→60일,
# 60m→2년 정도). "3분"은 Yahoo가 지원하지 않아 가장 가까운 5분으로 대체.
INTRADAY_OPTIONS = {
    "1분": ("1m", "5d"),
    "5분": ("5m", "1mo"),
    "15분": ("15m", "1mo"),
    "30분": ("30m", "3mo"),
    "1시간": ("60m", "6mo"),
}

# 한국 관행: 상승(종가>=시가)은 빨강, 하락은 파랑
_UP_COLOR = "#e74c3c"
_DOWN_COLOR = "#3498db"

# 타 증권사 앱처럼 클릭+드래그로 차트를 이동(pan)할 수 있게 — 기본값(zoom 박스선택) 대신.
# scrollZoom은 마우스 휠로 확대/축소, displaylogo는 plotly 로고 제거.
PLOTLY_CONFIG = {"scrollZoom": True, "displaylogo": False}


def render_price_chart_figure(df, period_days=None):
    """df: get_price_history() 결과 (Open/High/Low/Close/Volume 포함).
    period_days=None이면 전체 기간, 아니면 최근 N거래일만 표시."""
    ma20 = df["Close"].rolling(20).mean()
    ma60 = df["Close"].rolling(60).mean()

    view = df if period_days is None else df.tail(period_days)
    ma20_view = ma20.reindex(view.index)
    ma60_view = ma60.reindex(view.index)

    has_volume = "Volume" in view.columns
    fig = make_subplots(
        rows=2 if has_volume else 1, cols=1, shared_xaxes=True,
        row_heights=[0.65, 0.35] if has_volume else [1.0],
        vertical_spacing=0.05,
    )

    fig.add_trace(go.Candlestick(
        x=view.index, open=view["Open"], high=view["High"], low=view["Low"], close=view["Close"],
        name="가격", increasing_line_color=_UP_COLOR, decreasing_line_color=_DOWN_COLOR,
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=view.index, y=ma20_view, name="MA20", line=dict(width=1, color="#f39c12"),
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=view.index, y=ma60_view, name="MA60", line=dict(width=1, color="#8e44ad"),
    ), row=1, col=1)

    if has_volume:
        vol_colors = [_UP_COLOR if c >= o else _DOWN_COLOR for o, c in zip(view["Open"], view["Close"])]
        fig.add_trace(go.Bar(x=view.index, y=view["Volume"], name="거래량", marker_color=vol_colors),
                      row=2, col=1)
        # 거래량은 항상 0 이상이므로 축을 0부터 시작 — 안 그러면 자동 스케일이 음수 쪽까지
        # 잡아 늘려서 막대가 절반도 안 되는 높이로 눌려 보임(실제 겪은 문제)
        fig.update_yaxes(rangemode="tozero", title_text="거래량", row=2, col=1)

    fig.update_layout(
        height=520,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        dragmode="pan",
    )
    return fig


MAX_RELATIONSHIP_NODES = 10
_RELATIONSHIP_EDGE_COLORS = {
    "인수합병(M&A)": "#e74c3c",
    "공급 계약": "#2f6fed",
    "합작투자": "#8e44ad",
    "라이선싱": "#16a085",
    "전략적 제휴": "#f39c12",
    "공시상 언급": "#6b7280",  # 뉴스 기반 5개 유형과 구분되는 중립 회색 — SEC 공시(lib/sec_filings.py)
}
_RELATIONSHIP_HUB_COLOR = "#2f6fed"
_TERMINATED_STATUS = "철회·무산"
_MAX_PREVIEW_CHARS = 220


def _preview_text(headline_tuple):
    """헤드라인 튜플(dt, headline, url, status, context)에서 hover에 보여줄 문구를 고른다.
    실제 계약 문맥(뉴스 요약 또는 공시 원문에서 뽑은 스니펫)이 있으면 그걸 우선 쓰고,
    없으면(문서 fetch 실패 등) 기존처럼 헤드라인 그대로 — "언급됨"보다 "무슨 내용인지"를
    보여주는 게 목적이라 문맥이 있을 때는 반드시 그쪽을 택한다."""
    context = headline_tuple[4] if len(headline_tuple) > 4 else None
    text = context or headline_tuple[1]
    if len(text) > _MAX_PREVIEW_CHARS:
        text = text[:_MAX_PREVIEW_CHARS].rstrip() + "…"
    return text


def render_relationship_graph_figure(hub_ticker, hub_name, edges):
    """lib.qualitative.match_counterparties() 결과로 허브(현재 티커) 중심 원형 관계도를
    그린다. 노드 수가 항상 작아(peer+검색이력 매칭 기준) networkx 등 배치 라이브러리 없이
    단순 원형 배치로 충분하다. 같은 상대 회사에 대한 여러 엣지는 노드 1개로 합치고,
    유형(색)·최신 진행상태·근거 신뢰도·헤드라인은 hover에 모아 보여준다.
    최신 상태가 "철회·무산"이면 점선으로 표시 — 관계가 끝났다는 신호를 거리/색과 별개로
    선 스타일이라는 독립된 채널로 전달(오독 방지)."""
    grouped = {}
    for e in edges:
        g = grouped.setdefault(e["counterparty_ticker"], {
            "name": e["counterparty_name"], "types": [], "headlines": [], "evidence_levels": [],
            "latest_status": None, "latest_dt": -1,
        })
        if e["relationship_type"] not in g["types"]:
            g["types"].append(e["relationship_type"])
        if e.get("evidence_level") and e["evidence_level"] not in g["evidence_levels"]:
            g["evidence_levels"].append(e["evidence_level"])
        dt = e.get("datetime") or 0
        g["headlines"].append((dt, e["headline"], e.get("url"), e["status"], e.get("context")))
        if dt >= g["latest_dt"]:
            g["latest_dt"] = dt
            g["latest_status"] = e["status"]

    ordered = sorted(grouped.items(), key=lambda kv: (len(kv[1]["headlines"]), kv[1]["latest_dt"]), reverse=True)
    ordered = ordered[:MAX_RELATIONSHIP_NODES]

    fig = go.Figure()
    n = len(ordered)
    positions = {
        ticker: (math.cos(2 * math.pi * i / n), math.sin(2 * math.pi * i / n))
        for i, (ticker, _) in enumerate(ordered)
    }

    types_present = set()
    any_terminated = False
    for ticker, g in ordered:
        x, y = positions[ticker]
        primary_type = g["types"][0]
        types_present.add(primary_type)
        is_terminated = g["latest_status"] == _TERMINATED_STATUS
        any_terminated = any_terminated or is_terminated
        fig.add_trace(go.Scatter(
            x=[0, x], y=[0, y], mode="lines",
            line=dict(
                width=2, color=_RELATIONSHIP_EDGE_COLORS.get(primary_type, "#999"),
                dash="dot" if is_terminated else "solid",
            ),
            hoverinfo="skip", showlegend=False,
        ))

    # 범례는 실제로 등장한 유형만, 고정된 색 순서로(그래프마다 순서가 흔들리지 않게)
    for rel_type, color in _RELATIONSHIP_EDGE_COLORS.items():
        if rel_type in types_present:
            fig.add_trace(go.Scatter(
                x=[None], y=[None], mode="lines", line=dict(width=2, color=color), name=rel_type,
            ))
    if any_terminated:
        fig.add_trace(go.Scatter(
            x=[None], y=[None], mode="lines", line=dict(width=2, color="#999", dash="dot"),
            name="점선 = 철회·무산",
        ))

    fig.add_trace(go.Scatter(
        x=[0], y=[0], mode="markers+text", text=[hub_ticker], textposition="middle center",
        marker=dict(size=44, color=_RELATIONSHIP_HUB_COLOR), textfont=dict(color="white", size=13),
        hovertext=[hub_name], hoverinfo="text", showlegend=False,
    ))

    node_x, node_y, node_text, hover_text = [], [], [], []
    for ticker, g in ordered:
        x, y = positions[ticker]
        node_x.append(x)
        node_y.append(y)
        node_text.append(ticker)
        headlines_preview = "<br>".join(
            f"· [{h[3]}] {_preview_text(h)}" for h in sorted(g["headlines"], key=lambda h: h[0], reverse=True)[:5]
        )
        evidence_str = " / ".join(g["evidence_levels"]) or "근거 불명"
        hover_text.append(
            f"<b>{g['name'] or ticker}</b><br>{', '.join(g['types'])} · 최신 상태: {g['latest_status']}"
            f"<br>신뢰도: {evidence_str}<br>{headlines_preview}"
        )
    fig.add_trace(go.Scatter(
        x=node_x, y=node_y, mode="markers+text", text=node_text, textposition="bottom center",
        marker=dict(size=30, color="#f0f2f6", line=dict(width=2, color="#999")),
        hovertext=hover_text, hoverinfo="text", showlegend=False,
    ))

    fig.update_xaxes(visible=False, range=[-1.5, 1.5])
    fig.update_yaxes(visible=False, range=[-1.5, 1.5], scaleanchor="x", scaleratio=1)
    fig.update_layout(
        height=420,
        margin=dict(l=10, r=10, t=10, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig
