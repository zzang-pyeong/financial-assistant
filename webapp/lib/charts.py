"""최근 주가 캔들차트. 판단을 대신하지 않도록 매수/매도 신호 표시 없이
가격·이동평균·거래량만 병치해서 보여준다 (원칙 B)."""

import plotly.graph_objects as go
from plotly.subplots import make_subplots

PERIOD_OPTIONS = {"1개월": 21, "3개월": 63, "6개월": 126, "1년": 252, "전체": None}

# 한국 관행: 상승(종가>=시가)은 빨강, 하락은 파랑
_UP_COLOR = "#e74c3c"
_DOWN_COLOR = "#3498db"


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
        row_heights=[0.75, 0.25] if has_volume else [1.0],
        vertical_spacing=0.03,
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

    fig.update_layout(
        height=460,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
    return fig
