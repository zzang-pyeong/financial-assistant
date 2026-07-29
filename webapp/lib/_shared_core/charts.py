"""최근 주가 캔들차트. 판단을 대신하지 않도록 매수/매도 신호 표시 없이
가격·이동평균·거래량만 병치해서 보여준다 (원칙 B)."""

from pathlib import Path

import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components
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

# Streamlit의 기본 plotly 테마가 축 눈금·범례 글자를 옅은 회색으로 렌더링해 화면에서
# 흐리게 보인다는 피드백(2026-07-28) — 모든 차트 공통으로 진한 색을 명시해서 선명하게 한다.
CHART_TEXT_COLOR = "#1f2937"

# 타 증권사 앱처럼 클릭+드래그로 차트를 이동(pan)할 수 있게 — 기본값(zoom 박스선택) 대신.
# scrollZoom은 마우스 휠로 확대/축소, displaylogo는 plotly 로고 제거.
# ⚠️ 이건 가격 차트 전용이다(스크롤로 확대해서 보는 용도가 실제로 있음). 조작이 필요 없는
# 차트(재무제표 막대그래프 등)는 아래 STATIC_PLOTLY_CONFIG를 쓴다.
PLOTLY_CONFIG = {"scrollZoom": True, "displaylogo": False}

# 조작이 필요 없는 차트 전용(재무제표 막대그래프 등) — 조작을 전부 끄고 hover만 남긴다.
# 원래 관계도 전용으로 만들었다가(RELATIONSHIP_PLOTLY_CONFIG라는 이름이었음) 관계도가
# vis-network 컴포넌트로 바뀌면서(2026-07-29) 더는 안 쓰지만, 재무제표 등 같은 문제
# (커서가 차트 위에 있을 때 휠을 굴리면 페이지 스크롤 대신 차트가 확대/축소되던 문제)가
# 있는 다른 차트에서 계속 쓰므로 이름은 그대로 둔다.
STATIC_PLOTLY_CONFIG = {
    "scrollZoom": False,        # 휠은 페이지 스크롤로 넘긴다(이 문제의 직접 원인)
    "displayModeBar": False,    # 확대·저장 등 툴바 자체를 숨김
    "displaylogo": False,
    "doubleClick": False,       # 더블클릭 자동 확대 방지
    "showAxisDragHandles": False,
}


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
        font=dict(color=CHART_TEXT_COLOR),
    )
    return fig


def render_bar_chart_figure(series, color="#2f6fed", quarterly=False):
    """연도별/분기별 막대그래프(재무제표 추이용) — st.bar_chart 대신 plotly로 그려서
    STATIC_PLOTLY_CONFIG(스크롤·확대 비활성화)와 진한 글자색을 다른 차트와 통일한다.
    quarterly=True면 x축을 "2025 Q4"처럼 표시한다 — 그냥 strftime("%Y")를 쓰면 같은
    해의 분기 4개가 전부 "2025"로 겹쳐 보여서(실사용 화면에서 확인) 분기 구분이 안 됐다."""
    def _label(p):
        if quarterly:
            return f"{p.year} Q{(p.month - 1) // 3 + 1}"
        return p.strftime("%Y")

    fig = go.Figure(go.Bar(
        x=[_label(p) for p in series.index], y=series.values, marker_color=color,
    ))
    fig.update_layout(
        height=280,
        margin=dict(l=10, r=10, t=10, b=10),
        font=dict(color=CHART_TEXT_COLOR),
        xaxis=dict(fixedrange=True, tickfont=dict(color=CHART_TEXT_COLOR)),
        yaxis=dict(fixedrange=True, tickfont=dict(color=CHART_TEXT_COLOR)),
        dragmode=False,
    )
    return fig


# 관계 유형 목록·이름은 관계도 표준 스키마(직원 지시서)에 맞춘다 — "M&A"는 예전
# "인수합병(M&A)"의 축약형, "공급·고객 계약"은 "공급 계약"의 새 이름. 지분 투자·보유는
# 13D/13G 신규 추출(find_beneficial_owners)에서만 나온다. (자회사 유형은 추가했다가
# 제거함 — 투자 관점에서 의미가 낮은 법인 구조가 그래프를 도배해서.)
_RELATIONSHIP_EDGE_COLORS = {
    "M&A": "#e74c3c",
    "지분 투자·보유": "#e67e22",
    "공급·고객 계약": "#2f6fed",
    "합작투자": "#8e44ad",
    "라이선싱": "#16a085",
    "전략적 제휴": "#27ae60",  # 지분 투자·보유(#e67e22)와 너무 비슷한 주황이라 초록으로 변경
    "공시 내 언급": "#6b7280",  # 근거 등급 D — 나머지 유형과 구분되는 중립 회색
}
# 로고 없는 노드의 안쪽을 같은 색 계열의 아주 옅은 톤으로 채워 선-노드가 한 덩어리로
# 읽히게 한다. 채도를 낮게 잡는 이유: 진하게 칠하면 색이 "유불리"를 암시하는 것처럼
# 보이는데, 여기서 색은 관계 유형 구분일 뿐이다(원칙 B — 방향 색상 미사용).
_RELATIONSHIP_NODE_FILLS = {
    "M&A": "#fdecea",
    "지분 투자·보유": "#fdf0e3",
    "공급·고객 계약": "#eaf1fe",
    "합작투자": "#f3ecf8",
    "라이선싱": "#e8f6f3",
    "전략적 제휴": "#eafaf1",
    "공시 내 언급": "#f1f2f4",
}
_RELATIONSHIP_HUB_COLOR = "#2f6fed"
_TERMINATED_STATUS = "철회·무산"
_EVIDENCE_GRADE_RANK = {"A": 3, "B": 2, "C": 1, "D": 0}
# hover에 넣을 발췌문 길이. 전체 발췌문은 아래 근거 표에서 넉넉히 보므로 여기선 짧게 맛만 보인다.
_MAX_PREVIEW_CHARS = 150


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


# ---------------------------------------------------------------------------
# hover 한 줄 요약 합성 (2026-07-28, 관계도 2단계) — hover는 원문 발췌(영문)를 그대로
# 보여주는 대신, 1단계에서 채운 direction(outbound/inbound)과 유형을 조합해 한글 한 줄로
# 미리 합성해두고 원문 발췌는 보조 정보로 내린다. 방향이 "unknown"이면 화살표를 안 그리는
# 것과 같은 원칙으로, 화살표 방향을 문장으로 단정하지 않고 유형만 담백하게 말한다 —
# 근거 없는 확신을 만들지 않는다.
_SUPPLY_LIKE_TYPES = {"공급·고객 계약", "전략적 제휴", "라이선싱", "합작투자"}

# 방향을 못 정했을 때(unknown) 쓸 유형별 대체 문구 — 유형 이름 그대로 쓰기보다
# "공동개발"/"파트너십 체결"처럼 실제로 무슨 일이 있었는지를 담은 자연스러운 동사구를
# 쓴다. JV·전략적 제휴·라이선싱은 원래 방향(누가 누구에게)이라는 개념 자체가 상호적이라
# 없는 게 정상이므로, "미확인"이 아니라 이 문구로 대체한다. 여기 없는 유형은 원래
# 방향이 있어야 하는데 못 찾은 경우라 "미확인"을 그대로 쓴다 — 못 찾았다는 사실 자체를
# 감추지 않는다(원칙 7).
_NON_DIRECTIONAL_LABELS = {
    "합작투자": "공동개발",
    "전략적 제휴": "파트너십 체결",
    "라이선싱": "라이선스 계약",
}


def direction_label(direction, primary_type):
    """direction이 outbound/inbound/bidirectional이면 화살표 문구, 아니면(unknown)
    _NON_DIRECTIONAL_LABELS에 있는 유형은 그 담백한 한글 표현을, 없는 유형은 "미확인"을
    반환한다. hover 합성(_synthesize_relationship_line)과 요약표의 "방향" 컬럼
    (pages/8_관계도.py)이 같은 문구를 쓰도록 여기 한 곳에만 둔다."""
    if direction == "outbound":
        return "→ (당사→상대)"
    if direction == "inbound":
        return "← (상대→당사)"
    if direction == "bidirectional":
        return "↔ 상호"
    return _NON_DIRECTIONAL_LABELS.get(primary_type, "미확인")


def _synthesize_relationship_line(hub_ticker, cp_ticker_or_name, primary_type, direction, ownership_pct):
    """(허브 티커, 상대 표시명, 대표 관계유형, 방향, 지분율)로 한글 한 줄 요약을 만든다.
    방향이 뚜렷할 때만 "A → B" 화살표 문구를 쓰고, 모호하면 direction_label()의 유형별
    담백한 문구(또는 유형 이름)를 반환 — 근거 등급·문맥 없이 방향을 지어내지 않는다는
    원칙(원칙 7)을 hover 문구에도 그대로 적용."""
    cp = cp_ticker_or_name
    if primary_type == "지분 투자·보유":
        pct = f" {ownership_pct:.1f}%" if ownership_pct is not None else ""
        if direction == "inbound":
            return f"{cp}가 {hub_ticker} 지분{pct} 보유"
        if direction == "outbound":
            return f"{hub_ticker}가 {cp} 지분{pct} 보유"
        return f"지분 투자·보유{pct}"
    if primary_type == "M&A":
        if direction == "outbound":
            return f"{hub_ticker} → {cp} M&A(인수 측)"
        if direction == "inbound":
            return f"{cp} → {hub_ticker} M&A(피인수 측)"
        return "M&A"
    if primary_type in _SUPPLY_LIKE_TYPES:
        if direction == "outbound":
            return f"{hub_ticker} → {cp} 공급 ({primary_type})"
        if direction == "inbound":
            return f"{cp} → {hub_ticker} 공급 ({primary_type})"
        return direction_label(direction, primary_type)
    return primary_type or "공시 내 언급"


def group_relationship_edges(edges):
    """엣지 목록을 상대 회사 단위로 묶어 (티커, 정보) 리스트를 근거 수·최신순으로 정렬해
    반환한다. 그래프와 그래프 아래 근거 표(전체)가 **같은 그룹핑·같은 정렬**을 쓰도록
    여기 한 곳에만 둔다 — 예전엔 그래프 함수 안에 묻혀 있어서, 표를 따로 만들면 "그래프에
    보이는 순서"와 "표의 순서"가 조용히 갈라질 수 있었다.

    news_count/filing_count를 나눠 세는 이유: 근거 표에서 "이 회사는 뉴스로 잡힌 건가,
    공시로 잡힌 건가"가 신뢰도 판단의 핵심인데, 합계만으로는 구분이 안 되기 때문이다.

    13D/13G 대량 지분 보유자는 개인·비상장 펀드가 많아 티커가 없는 경우가 흔하다
    (find_beneficial_owners 참고) — 그때는 counterparty_ticker가 빈 문자열이라, 그대로
    묶는 키로 쓰면 티커 없는 보유자가 전부 한 그룹으로 합쳐진다. 그래서 티커가 없으면
    이름을 대신 키로 쓴다.

    direction/best_grade/ownership_pct는 근거 등급이 가장 높은 엣지 기준으로 채택한다 —
    같은 상대기업에 등급이 다른 근거가 섞여 있어도(예: 13D/13G A등급 + 뉴스 C등급)
    가장 신뢰도 높은 근거의 값을 대표값으로 쓴다."""
    grouped = {}
    for e in edges:
        key = e["counterparty_ticker"] or e["counterparty_name"]
        g = grouped.setdefault(key, {
            "name": e["counterparty_name"], "types": [], "headlines": [], "evidence_levels": [],
            "latest_status": None, "latest_dt": -1, "news_count": 0, "filing_count": 0,
            "direction": "unknown", "best_grade": "D", "ownership_pct": None,
        })
        if e["relationship_type"] not in g["types"]:
            g["types"].append(e["relationship_type"])
        if e.get("evidence_level") and e["evidence_level"] not in g["evidence_levels"]:
            g["evidence_levels"].append(e["evidence_level"])
        dt = e.get("datetime") or 0
        # 6번째 원소(relationship_type)는 근거 표에서 "이게 뉴스인지 공시인지"를 판정하는 데
        # 쓴다 — 상태 문자열("공시 확인")을 문자열 검사로 넘겨짚던 것보다 안전하다.
        # 앞 5개 순서는 _preview_text()가 인덱스로 참조하므로 바꾸지 말 것. 7·8번째(등급/
        # 소스)는 근거 원문 표(pages/8_관계도.py)가 쓰려고 뒤에 덧붙인 것 — 기존 인덱스와
        # 겹치지 않게 항상 끝에만 추가할 것.
        g["headlines"].append((
            dt, e["headline"], e.get("url"), e["status"], e.get("context"), e["relationship_type"],
            e.get("evidence_grade", "D"), e.get("source_kind", ""),
        ))
        # source_kind로 판정한다(relationship_type 문자열이 아니라) — "공시 내 언급"이
        # promote_mentions_with_context()로 "공급·고객 계약" 등으로 승격돼도 source_kind는
        # 그대로 "SEC 공시"라 승격된 엣지도 여전히 filing_count로 잡힌다.
        if e.get("source_kind") == "SEC 공시":
            g["filing_count"] += 1
        else:
            g["news_count"] += 1
        if dt >= g["latest_dt"]:
            g["latest_dt"] = dt
            g["latest_status"] = e["status"]

        grade = e.get("evidence_grade", "D")
        if _EVIDENCE_GRADE_RANK.get(grade, 0) >= _EVIDENCE_GRADE_RANK.get(g["best_grade"], 0):
            g["best_grade"] = grade
            g["direction"] = e.get("direction", "unknown")
        if e.get("ownership_pct") is not None:
            g["ownership_pct"] = e["ownership_pct"]

    return sorted(
        grouped.items(),
        key=lambda kv: (len(kv[1]["headlines"]), kv[1]["latest_dt"]),
        reverse=True,
    )


# ---------------------------------------------------------------------------
# 관계도 렌더링 — vis-network.js (2026-07-29, EveryTie 참고로 Plotly 고정 링 배치에서
# 교체). 물리 기반 force-directed 레이아웃이라 드래그·확대·자연스러운 군집이 전부
# 공짜로 딸려온다 — 예전엔 이걸 전부 손으로 계산했다(_node_positions 각도/반지름 수학,
# cluster_by_sector 섹터 재배열). 컴포넌트 코드는
# lib/page8_only_relationship/relationship_graph_component/index.html.
# ---------------------------------------------------------------------------
_COMPONENT_DIR = (
    Path(__file__).resolve().parent.parent / "page8_only_relationship" / "relationship_graph_component"
)
_relationship_network_component = components.declare_component(
    "relationship_graph", path=str(_COMPONENT_DIR),
)


def _node_title_html(hub_ticker, ticker, g):
    """노드 hover에 쓸 HTML. 예전 Plotly 버전은 hover 텍스트를 손으로 줄바꿈해야 했다
    (plotly가 자동 줄바꿈을 안 해줘서, _wrap_hover/_display_width 참고— 이제 삭제됨) —
    vis-network 네이티브 tooltip은 CSS(white-space:normal, max-width)로 알아서 줄바꿈해서
    그 손수 wrap 로직 자체가 필요 없어졌다."""
    headlines_preview = "<br>".join(
        f"· [{h[3]}] {_preview_text(h)}"
        for h in sorted(g["headlines"], key=lambda h: h[0], reverse=True)[:2]
    )
    source_str = " · ".join(filter(None, [
        f"뉴스 {g['news_count']}건" if g["news_count"] else "",
        f"공시 {g['filing_count']}건" if g["filing_count"] else "",
    ]))
    synth_line = _synthesize_relationship_line(
        hub_ticker, ticker, g["types"][0], g.get("direction", "unknown"), g.get("ownership_pct"),
    )
    return (
        f"<b>{g['name'] or ticker}</b> ({ticker})<br><b>{synth_line}</b>"
        f"<br>최신 상태: {g['latest_status']} · 근거: {source_str}"
        f"<br><br>근거 원문: {headlines_preview}"
    )


def _logo_src(logo):
    if not logo:
        return None
    return logo.get("src") if isinstance(logo, dict) else logo


def render_relationship_network(hub_ticker, hub_name, edges, logos=None, key=None):
    """허브(현재 티커) 중심 관계도를 vis-network 컴포넌트로 그린다. 상대기업을 상위 몇
    개로 자르지 않고 전부 그린다. 같은 상대 회사에 대한 여러 엣지는 노드 1개로 합치고,
    유형은 색, 최신 진행상태가 "철회·무산"이면 점선으로 표시한다 — 관계가 끝났다는 신호를
    색과 별개로 선 스타일이라는 독립된 채널로 전달(오독 방지).

    logos: {티커: `lib/page8_only_relationship/logos.py::get_circular_logo()` 결과 또는
    URL 문자열} — 있으면 노드를 그 로고 이미지로(vis-network의 circularImage 셰이프가
    사각형 이미지도 원 안에 알아서 잘라 넣어준다 — 예전 Plotly 버전처럼 서버에서
    "원형으로 잘랐는지" 구분해서 크기를 다르게 줄 필요가 없어졌다). 없으면 유형별 옅은
    색 배경의 빈 원.

    반환값: 클릭된 상대기업 티커, 또는 아무것도 안 눌렀으면 None(허브 클릭도 None —
    자기 자신으로 재검색되는 걸 막으려고 컴포넌트 쪽에서 걸러준다).

    ⚠️ 노드 크기는 근거 개수와 무관하게 전부 같다. 크기로 굵기를 주면 "근거가 많다 =
    관계가 더 확실하다"는 뜻으로 읽히는데, 그건 이 제품이 하지 않기로 한 집계다(원칙 B).
    개수는 그래프 아래 근거 표에서 숫자 그대로 확인한다."""
    logos = logos or {}
    ordered = group_relationship_edges(edges)

    hub_src = _logo_src(logos.get(hub_ticker))
    hub_node = {
        "id": hub_ticker, "label": hub_ticker, "size": 34,
        "fixed": {"x": True, "y": True}, "x": 0, "y": 0,
        "titleHtml": f"<b>{hub_name}</b> ({hub_ticker})",
    }
    if hub_src:
        hub_node.update(
            shape="circularImage", image=hub_src, borderWidth=4,
            color={"border": _RELATIONSHIP_HUB_COLOR, "background": "#ffffff"},
            font={"size": 14, "color": _RELATIONSHIP_HUB_COLOR, "bold": True},
        )
    else:
        hub_node.update(
            shape="dot",
            color={"border": _RELATIONSHIP_HUB_COLOR, "background": _RELATIONSHIP_HUB_COLOR},
            font={"size": 14, "color": "#ffffff", "bold": True},
        )
    nodes = [hub_node]

    edges_out = []
    for ticker, g in ordered:
        primary_type = g["types"][0]
        border = _RELATIONSHIP_EDGE_COLORS.get(primary_type, "#9aa0a6")
        src = _logo_src(logos.get(ticker))
        node = {
            "id": ticker, "label": ticker, "size": 24,
            "titleHtml": _node_title_html(hub_ticker, ticker, g),
        }
        if src:
            node.update(
                shape="circularImage", image=src,
                color={"border": border, "background": "#ffffff"},
            )
        else:
            fill = _RELATIONSHIP_NODE_FILLS.get(primary_type, "#f1f2f4")
            node.update(shape="dot", color={"border": border, "background": fill})
        nodes.append(node)

        direction = g.get("direction", "unknown")
        arrows = {}
        if direction == "outbound":
            arrows = {"to": {"enabled": True, "scaleFactor": 0.6}}
        elif direction == "inbound":
            arrows = {"from": {"enabled": True, "scaleFactor": 0.6}}
        elif direction == "bidirectional":
            arrows = {
                "to": {"enabled": True, "scaleFactor": 0.6},
                "from": {"enabled": True, "scaleFactor": 0.6},
            }
        edges_out.append({
            "from": hub_ticker, "to": ticker, "color": border,
            "dashes": g["latest_status"] == _TERMINATED_STATUS, "arrows": arrows,
        })

    # 노드가 많을수록 물리 시뮬레이션이 펼쳐질 공간이 더 필요하다 — 12개까지는 기본
    # 높이, 그 이상은 조금씩 키우되 너무 길어지지 않게 상한을 둔다.
    height = 420 if len(ordered) <= 12 else min(760, 420 + (len(ordered) - 12) * 12)

    return _relationship_network_component(
        nodes=nodes, edges=edges_out, hubId=hub_ticker, height=height, key=key, default=None,
    )


def render_relationship_legend(edges):
    """그래프 위에 붙이는 색상 범례. 예전엔 Plotly 더미 trace로 그렸지만(범례 자체가
    Plotly 기능), vis-network 컴포넌트는 그런 게 없어서 실제로 등장한 유형만 골라
    HTML로 직접 그린다 — 색 순서는 render_relationship_network가 쓰는 것과 동일하게
    고정 순서(그래프마다 순서가 흔들리지 않게)."""
    types_present = {e["relationship_type"] for e in edges}
    any_terminated = any(e["status"] == _TERMINATED_STATUS for e in edges)

    items = [
        f"<span style='display:inline-flex; align-items:center; gap:0.35rem; margin-right:1.1rem;'>"
        f"<span style='width:14px; height:3px; background:{color}; display:inline-block; "
        f"border-radius:2px;'></span>{rel_type}</span>"
        for rel_type, color in _RELATIONSHIP_EDGE_COLORS.items() if rel_type in types_present
    ]
    if any_terminated:
        items.append(
            "<span style='display:inline-flex; align-items:center; gap:0.35rem;'>"
            "<span style='width:14px; height:0; border-top:3px dashed #9aa0a6; "
            "display:inline-block;'></span>점선 = 철회·무산</span>"
        )
    st.markdown(
        f"<div style='font-size:0.8rem; color:#3c4043; margin-bottom:0.6rem;'>{''.join(items)}</div>",
        unsafe_allow_html=True,
    )
