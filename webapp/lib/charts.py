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
# ⚠️ 이건 가격 차트 전용이다. 관계도는 아래 RELATIONSHIP_PLOTLY_CONFIG를 쓴다.
PLOTLY_CONFIG = {"scrollZoom": True, "displaylogo": False}

# 관계도 전용 — 조작을 전부 끄고 hover만 남긴다.
# 이유: 관계도는 그래프 아래에 근거 표가 길게 붙어서 사용자가 반드시 스크롤을 내려야 하는데,
# 커서가 그래프 위에 있는 동안 휠을 굴리면 페이지가 안 내려가고 그래프가 확대/축소돼 버렸다
# (가격 차트와 같은 config를 공유하고 있었던 탓). 관계도는 확대·이동해서 볼 이유도 없다 —
# 노드가 10개뿐이고 좌표에 의미가 없다(원형 배치는 그냥 배치일 뿐).
# staticPlot=True로 하면 hover까지 죽어서 쓸 수 없다 — 개별 옵션으로 끈다.
RELATIONSHIP_PLOTLY_CONFIG = {
    "scrollZoom": False,        # 휠은 페이지 스크롤로 넘긴다(이 문제의 직접 원인)
    "displayModeBar": False,    # 확대·저장 등 툴바 자체를 숨김
    "displaylogo": False,
    "doubleClick": False,       # 더블클릭 자동 확대 방지
    "showAxisDragHandles": False,
}

# hover 말풍선 한 줄의 최대 표시 폭(한글은 2, 그 외는 1로 계산). plotly는 hover 텍스트를
# 자동 줄바꿈하지 않아서, 긴 줄이 있으면 말풍선이 그림 영역보다 넓어지고 화면 밖으로
# 잘려 나간다 — 공시 발췌문(영문 장문)에서 실제로 발생했다.
_HOVER_WIDTH = 92


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
# 노드 안쪽을 같은 색 계열의 아주 옅은 톤으로 채워 선-노드가 한 덩어리로 읽히게 한다.
# 채도를 낮게 잡는 이유: 진하게 칠하면 색이 "유불리"를 암시하는 것처럼 보이는데, 여기서
# 색은 관계 유형 구분일 뿐이다(원칙 B — 방향 색상 미사용).
_RELATIONSHIP_NODE_FILLS = {
    "인수합병(M&A)": "#fdecea",
    "공급 계약": "#eaf1fe",
    "합작투자": "#f3ecf8",
    "라이선싱": "#e8f6f3",
    "전략적 제휴": "#fef5e7",
    "공시상 언급": "#f1f2f4",
}
_RELATIONSHIP_HUB_COLOR = "#2f6fed"
_TERMINATED_STATUS = "철회·무산"
# hover에 넣을 발췌문 길이. 220자였는데 줄바꿈을 넣으면 그것만 3~4줄이 되어 말풍선이
# 그래프를 덮었다 — 전체 발췌문은 아래 근거 표에서 넉넉히 보므로 여기선 짧게 맛만 보인다.
_MAX_PREVIEW_CHARS = 150

# 노드가 이 개수를 넘으면 반지름을 번갈아 다르게 줘서 라벨이 서로 겹치는 걸 막는다
# (10개를 같은 반지름 원에 두면 좌우 3~4시 방향에서 회사명이 붙어버린다).
_STAGGER_FROM = 6
_RADIUS_NEAR = 1.0
_RADIUS_FAR = 1.24

# 노드 원의 크기 — 픽셀(marker size)이 아니라 **데이터 좌표** 단위다.
# 로고를 넣으려면 이래야 한다: plotly의 layout image는 데이터 좌표로 배치되는데 marker는
# 픽셀 단위라, 원은 픽셀이고 로고는 데이터 단위면 창 크기가 바뀔 때 로고가 원 밖으로
# 삐져나온다. 원 자체를 shape(데이터 좌표)로 그려서 둘이 항상 같이 움직이게 했다.
_NODE_RADIUS = 0.135
_HUB_RADIUS = 0.19
# 로고 크기 배율 — 로고가 이미 원형으로 가공됐는지에 따라 둘 중 하나를 쓴다.
#
# _LOGO_FIT_CIRCULAR: 원형 PNG(lib/logos.py가 가운데를 원으로 잘라 알파 마스크를 씌운 것)는
#   모서리가 없으니 원을 꽉 채운다. 다만 지름을 원과 똑같이(2.0) 주면 이미지가 테두리 선을
#   덮어버려 유형별 색 링이 사라진다 — plotly는 image를 shape 위에 그리기 때문이다.
#   그래서 살짝 안쪽에 앉혀(0.92) 링과 흰 여백이 남게 한다.
# _LOGO_FIT_SQUARE: 가공에 실패한(예: SVG) 네모난 이미지는 예전처럼 원에 내접시킨다.
#   내접 정사각형의 한 변은 반지름의 √2(≈1.41)이므로 그보다 크면 모서리가 삐져나온다.
_LOGO_FIT_CIRCULAR = 1.84
_LOGO_FIT_SQUARE = 1.41


def _display_width(text):
    """한글·한자·일본어는 라틴 문자의 약 두 배 폭을 차지하므로 2로 센다 — hover에 한글
    설명과 영문 공시 발췌문이 섞여 있어서, 글자 수로만 재면 한글 줄이 훨씬 길어진다."""
    return sum(2 if ord(ch) > 0x2E7F else 1 for ch in text)


def _wrap_hover(text, width=_HOVER_WIDTH):
    """hover 텍스트를 단어 경계에서 직접 줄바꿈한다(plotly가 안 해준다).

    이미 들어있는 <br>은 그대로 살리고, 그보다 긴 줄만 쪼갠다. 공백 없이 긴 토큰
    (URL 등)은 단어 경계가 없으니 폭에 맞춰 강제로 끊는다 — 안 그러면 그 줄 하나 때문에
    말풍선 전체가 화면 밖으로 잘린다."""
    lines = []
    for raw_line in text.split("<br>"):
        if _display_width(raw_line) <= width:
            lines.append(raw_line)
            continue
        current = ""
        for word in raw_line.split(" "):
            # 단어 자체가 한 줄보다 길면 폭 단위로 잘라 넣는다
            while _display_width(word) > width:
                head = ""
                for ch in word:
                    if _display_width(head + ch) > width:
                        break
                    head += ch
                if current:
                    lines.append(current)
                    current = ""
                lines.append(head)
                word = word[len(head):]
            if not word:
                continue
            candidate = f"{current} {word}" if current else word
            if current and _display_width(candidate) > width:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
    return "<br>".join(lines)


def _add_node_circle(fig, x, y, radius, fillcolor, linecolor, width=2):
    """노드 원을 데이터 좌표 shape으로 그린다(로고와 같은 좌표계를 쓰기 위함).
    layer="below"는 trace(선·라벨) 기준이며, 선은 이미 원 테두리에서 끊기므로 겹치지 않는다."""
    fig.add_shape(
        type="circle", xref="x", yref="y", layer="below",
        x0=x - radius, x1=x + radius, y0=y - radius, y1=y + radius,
        fillcolor=fillcolor, line=dict(color=linecolor, width=width),
    )


def _add_logo_image(fig, x, y, radius, logo):
    """원 안에 로고를 앉힌다. logo는 lib/logos.py::get_circular_logo()가 주는
    {"src":..., "circular": bool} 형태이거나, 그냥 URL 문자열이어도 된다(문자열이면
    네모난 이미지로 보고 내접시킨다).

    circular=True면 이미지 자체가 원형이라 원을 거의 꽉 채우고, False면 모서리가
    삐져나오지 않게 내접시킨다. sizing="contain"으로 비율을 보존하므로 어느 쪽이든
    이미지가 찌그러지지는 않는다. 이미지를 못 받아오면 plotly가 조용히 아무것도 안 그려서
    자동으로 '빈 원'(로고 기능 추가 전 모습)으로 폴백된다."""
    if isinstance(logo, str):
        src, circular = logo, False
    else:
        src, circular = logo.get("src"), bool(logo.get("circular"))
    if not src:
        return
    side = radius * (_LOGO_FIT_CIRCULAR if circular else _LOGO_FIT_SQUARE)
    fig.add_layout_image(
        source=src, xref="x", yref="y", x=x, y=y,
        sizex=side, sizey=side, xanchor="center", yanchor="middle",
        sizing="contain", layer="above", opacity=1,
    )


def _edge_endpoints(x, y):
    """허브에서 노드로 가는 선을, 양쪽 원의 테두리에서 시작·종료하도록 잘라 반환한다.
    중심에서 중심으로 그으면 선이 원 내부를 가로질러 로고 위에 겹친다."""
    dist = math.hypot(x, y) or 1.0
    ux, uy = x / dist, y / dist
    start = (ux * _HUB_RADIUS, uy * _HUB_RADIUS)
    end = (ux * (dist - _NODE_RADIUS), uy * (dist - _NODE_RADIUS))
    return start, end


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


def group_relationship_edges(edges):
    """엣지 목록을 상대 회사 단위로 묶어 (티커, 정보) 리스트를 근거 수·최신순으로 정렬해
    반환한다. 그래프(상위 N개만)와 그래프 아래 근거 표(전체)가 **같은 그룹핑·같은 정렬**을
    쓰도록 여기 한 곳에만 둔다 — 예전엔 그래프 함수 안에 묻혀 있어서, 표를 따로 만들면
    "그래프에 보이는 순서"와 "표의 순서"가 조용히 갈라질 수 있었다.

    news_count/filing_count를 나눠 세는 이유: 근거 표에서 "이 회사는 뉴스로 잡힌 건가,
    공시로 잡힌 건가"가 신뢰도 판단의 핵심인데, 합계만으로는 구분이 안 되기 때문이다."""
    grouped = {}
    for e in edges:
        g = grouped.setdefault(e["counterparty_ticker"], {
            "name": e["counterparty_name"], "types": [], "headlines": [], "evidence_levels": [],
            "latest_status": None, "latest_dt": -1, "news_count": 0, "filing_count": 0,
        })
        if e["relationship_type"] not in g["types"]:
            g["types"].append(e["relationship_type"])
        if e.get("evidence_level") and e["evidence_level"] not in g["evidence_levels"]:
            g["evidence_levels"].append(e["evidence_level"])
        dt = e.get("datetime") or 0
        # 6번째 원소(relationship_type)는 근거 표에서 "이게 뉴스인지 공시인지"를 판정하는 데
        # 쓴다 — 상태 문자열("공시 확인")을 문자열 검사로 넘겨짚던 것보다 안전하다.
        # 앞 5개 순서는 _preview_text()가 인덱스로 참조하므로 바꾸지 말 것.
        g["headlines"].append((
            dt, e["headline"], e.get("url"), e["status"], e.get("context"), e["relationship_type"],
        ))
        if e["relationship_type"] == "공시상 언급":
            g["filing_count"] += 1
        else:
            g["news_count"] += 1
        if dt >= g["latest_dt"]:
            g["latest_dt"] = dt
            g["latest_status"] = e["status"]

    return sorted(
        grouped.items(),
        key=lambda kv: (len(kv[1]["headlines"]), kv[1]["latest_dt"]),
        reverse=True,
    )


def _node_positions(count):
    """허브를 중심으로 12시 방향에서 시계방향으로 노드를 배치한 좌표 목록.

    12시에서 시계방향인 이유는 단순히 읽는 순서와 맞아서다(기존엔 3시에서 반시계방향이라
    "가장 근거가 많은 회사"가 오른쪽 옆구리에서 시작했다). 노드가 많아지면 반지름을
    번갈아 바꿔 라벨이 겹치지 않게 한다."""
    positions = []
    for i in range(count):
        angle = math.pi / 2 - 2 * math.pi * i / count
        radius = _RADIUS_NEAR
        if count >= _STAGGER_FROM and i % 2 == 1:
            radius = _RADIUS_FAR
        positions.append((radius * math.cos(angle), radius * math.sin(angle)))
    return positions


def render_relationship_graph_figure(hub_ticker, hub_name, edges, logos=None):
    """허브(현재 티커) 중심 원형 관계도. 노드 수가 항상 작아(상위 10개) networkx 등 배치
    라이브러리 없이 단순 원형 배치로 충분하다. 같은 상대 회사에 대한 여러 엣지는 노드
    1개로 합치고, 유형은 색, 최신 진행상태가 "철회·무산"이면 점선으로 표시한다 — 관계가
    끝났다는 신호를 색과 별개로 선 스타일이라는 독립된 채널로 전달(오독 방지).

    logos: {티커: `lib/logos.py::get_circular_logo()` 결과} — 있으면 노드 원 안에 로고를
    넣는다. 이 함수는 네트워크를 타지 않는다(순수 렌더링 유지). 로고 수집·가공은 호출부
    (pages/8_관계도.py)가 담당하고, 없는 티커는 그냥 빠지면 된다 — 로고 없는 노드는 로고
    기능 추가 전과 똑같이 빈 원으로 그려진다.

    ⚠️ 노드 크기는 근거 개수와 무관하게 전부 같다. 크기로 굵기를 주면 "근거가 많다 =
    관계가 더 확실하다"는 뜻으로 읽히는데, 그건 이 제품이 하지 않기로 한 집계다(원칙 B).
    개수는 그래프 아래 근거 표에서 숫자 그대로 확인한다."""
    logos = logos or {}
    ordered = group_relationship_edges(edges)[:MAX_RELATIONSHIP_NODES]

    fig = go.Figure()
    coords = _node_positions(len(ordered))

    types_present = set()
    any_terminated = False
    for (ticker, g), (x, y) in zip(ordered, coords):
        primary_type = g["types"][0]
        types_present.add(primary_type)
        is_terminated = g["latest_status"] == _TERMINATED_STATUS
        any_terminated = any_terminated or is_terminated
        # 선을 노드 중심까지 긋지 않고 원 테두리에서 끊는다 — 중심까지 그으면 선이 원 안을
        # 가로질러 로고 위에 겹쳐 보인다(로고를 넣기 전에는 원이 비어 있어 티가 안 나던 부분).
        (sx, sy), (ex, ey) = _edge_endpoints(x, y)
        fig.add_trace(go.Scatter(
            x=[sx, ex], y=[sy, ey], mode="lines",
            line=dict(
                width=1.6, color=_RELATIONSHIP_EDGE_COLORS.get(primary_type, "#9aa0a6"),
                dash="dot" if is_terminated else "solid",
            ),
            opacity=0.75, hoverinfo="skip", showlegend=False,
        ))

    # 범례는 실제로 등장한 유형만, 고정된 색 순서로(그래프마다 순서가 흔들리지 않게)
    for rel_type, color in _RELATIONSHIP_EDGE_COLORS.items():
        if rel_type in types_present:
            fig.add_trace(go.Scatter(
                x=[None], y=[None], mode="lines", line=dict(width=2, color=color), name=rel_type,
            ))
    if any_terminated:
        fig.add_trace(go.Scatter(
            x=[None], y=[None], mode="lines", line=dict(width=2, color="#9aa0a6", dash="dot"),
            name="점선 = 철회·무산",
        ))

    node_x, node_y, node_text, hover_text, text_positions = [], [], [], [], []
    for (ticker, g), (x, y) in zip(ordered, coords):
        primary_type = g["types"][0]
        border = _RELATIONSHIP_EDGE_COLORS.get(primary_type, "#9aa0a6")
        logo_url = logos.get(ticker)
        # 로고가 있으면 원 안쪽은 흰색으로 — 옅은 색조 위에 로고를 얹으면 로고의 흰 배경과
        # 원 배경이 어긋나 얼룩덜룩해 보인다. 로고가 없으면 기존처럼 유형별 옅은 색조를 쓴다.
        fill = "white" if logo_url else _RELATIONSHIP_NODE_FILLS.get(primary_type, "#f1f2f4")
        _add_node_circle(fig, x, y, _NODE_RADIUS, fill, border, width=2)
        if logo_url:
            _add_logo_image(fig, x, y, _NODE_RADIUS, logo_url)

        node_x.append(x)
        node_y.append(y)
        node_text.append(ticker)
        # 라벨은 로고 유무와 무관하게 항상 원 바깥(허브 반대편)에 둔다 — 로고만으로는 어느
        # 회사인지 못 알아보는 경우가 많고, 로고 있는 노드와 없는 노드의 라벨 위치가 달라지면
        # 눈이 훑을 때 줄이 안 맞아 더 어수선해진다.
        text_positions.append("top center" if y >= 0 else "bottom center")

        # 아래 근거 표가 전체를 다 보여주므로 hover는 최신 2건까지만 — 말풍선이 화면을
        # 덮을 만큼 길어지면 정작 그래프가 안 보인다.
        headlines_preview = "<br>".join(
            f"· [{h[3]}] {_preview_text(h)}"
            for h in sorted(g["headlines"], key=lambda h: h[0], reverse=True)[:2]
        )
        source_str = " · ".join(filter(None, [
            f"뉴스 {g['news_count']}건" if g["news_count"] else "",
            f"공시 {g['filing_count']}건" if g["filing_count"] else "",
        ]))
        hover_text.append(_wrap_hover(
            f"<b>{g['name'] or ticker}</b> ({ticker})<br>{', '.join(g['types'])}"
            f" · 최신 상태: {g['latest_status']}<br>근거: {source_str}"
            f"<br><br>{headlines_preview}<br><br><i>원문 링크와 전체 근거는 아래 표에 있습니다</i>"
        ))

    # 원은 shape으로 그렸으므로, 이 trace는 (1) 라벨 (2) hover 판정 영역 역할만 한다.
    # 마커를 완전 투명하게 두는 이유: 원 위에 또 원을 겹쳐 그리면 테두리가 두 겹으로 보인다.
    # 투명해도 hover 판정은 살아있다.
    fig.add_trace(go.Scatter(
        x=node_x, y=node_y, mode="markers+text", text=node_text, textposition=text_positions,
        marker=dict(size=38, color="rgba(0,0,0,0)"),
        textfont=dict(size=12, color="#3c4043"),
        hovertext=hover_text, hoverinfo="text", showlegend=False,
    ))

    # 허브 — 로고가 있으면 흰 원 + 굵은 파란 테두리(중심임을 테두리로 표현), 없으면 예전처럼
    # 파랑으로 꽉 채우고 흰 글씨로 티커를 넣는다.
    hub_logo = logos.get(hub_ticker)
    if hub_logo:
        _add_node_circle(fig, 0, 0, _HUB_RADIUS, "white", _RELATIONSHIP_HUB_COLOR, width=4)
        _add_logo_image(fig, 0, 0, _HUB_RADIUS, hub_logo)
        fig.add_trace(go.Scatter(
            x=[0], y=[0], mode="markers+text", text=[hub_ticker], textposition="bottom center",
            marker=dict(size=52, color="rgba(0,0,0,0)"),
            textfont=dict(size=13, color=_RELATIONSHIP_HUB_COLOR, family="Arial Black, sans-serif"),
            hovertext=[hub_name], hoverinfo="text", showlegend=False,
        ))
    else:
        fig.add_trace(go.Scatter(
            x=[0], y=[0], mode="markers+text", text=[hub_ticker], textposition="middle center",
            marker=dict(size=52, color=_RELATIONSHIP_HUB_COLOR, line=dict(width=3, color="white")),
            textfont=dict(color="white", size=13, family="Arial Black, sans-serif"),
            hovertext=[hub_name], hoverinfo="text", showlegend=False,
        ))

    # 라벨이 노드 바깥에 붙으므로 축 범위를 반지름보다 넉넉히 잡아야 잘리지 않는다.
    # fixedrange=True로 축 확대/축소를 아예 막는다 — 관계도는 좌표에 의미가 없어서(원형
    # 배치는 배치일 뿐) 확대해서 볼 것이 없고, 사용자가 스크롤로 아래 표를 보려다 실수로
    # 그래프를 확대해버리는 일을 막는 게 훨씬 중요하다.
    span = _RADIUS_FAR + _NODE_RADIUS + 0.42
    fig.update_xaxes(visible=False, range=[-span, span], fixedrange=True)
    fig.update_yaxes(
        visible=False, range=[-span, span], scaleanchor="x", scaleratio=1, fixedrange=True,
    )
    fig.update_layout(
        height=520,
        margin=dict(l=10, r=10, t=10, b=10),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.01, x=0.5, xanchor="center",
            font=dict(size=11), bgcolor="rgba(0,0,0,0)",
        ),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        dragmode=False,  # 드래그로 이동/영역선택하는 동작 제거 (hover는 그대로 살아있다)
        hoverlabel=dict(align="left", bgcolor="white", font=dict(size=12)),
    )
    return fig
