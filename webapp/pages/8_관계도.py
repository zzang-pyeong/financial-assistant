import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.append(str(Path(__file__).parent.parent))

from lib.page_helpers import require_analysis, inject_base_styles, render_wordmark
from lib.search import render_sidebar
from lib.charts import (
    render_relationship_graph_figure, group_relationship_edges,
    RELATIONSHIP_PLOTLY_CONFIG, SECTOR_CLUSTER_THRESHOLD,
)
from lib.known_companies import STATIC_KNOWN_COMPANIES
from lib.sec_filings import (
    find_filing_relationships, attach_context_snippets,
    find_subsidiaries, find_beneficial_owners,
)
from lib.logos import get_circular_logos
from lib.sectors import get_sectors
from lib.translate import to_korean, prefetch_korean

st.set_page_config(page_title="Connection Map — EnterTicker", layout="wide")
inject_base_styles()
require_analysis()

with st.sidebar:
    render_sidebar()

ticker = st.session_state.ticker
with st.container(key="page_header"):
    render_wordmark("Connection", "Map", align="center")
    st.caption(f"{ticker} · 기업 연결 근거")
st.divider()

# 목적 문장 + 경고 문장은 항상 보이게(작업 지시서 5절) — 나머지 상세 주의사항은
# 펼쳐야 보이는 expander로 분리해 화면을 덜 뒤덮게 한다.
st.markdown(
    "**검색한 기업의 M&A, 지분 보유, 자회사, 계약·제휴 연결을 원문 근거와 함께 탐색합니다.**"
)
st.caption("⚠️ 공시 내 언급은 실제 거래 관계가 아닐 수 있으며 기본 화면에서는 숨깁니다.")
with st.expander("이 화면을 읽을 때 알아둘 점"):
    st.markdown(
        "- **자회사·지분 보유는 공식 SEC 문서(Exhibit 21, Schedule 13D/13G)를 우선 근거로 "
        "합니다** — 근거 등급 A.\n"
        "- **뉴스 기반 관계(M&A·계약·제휴)는 공식 확인 전 보도일 수 있습니다** — 근거 등급 C.\n"
        "- **공시 내 언급은 문맥이 다양합니다.** 경쟁사 비교, 소송 상대, 위험요인 섹션의 "
        "나열 등 실제 거래관계가 아닐 수 있습니다 — 기본 화면에서는 숨기고, 아래 토글로 "
        "켜야 보입니다.\n"
        "- **목록 밖 회사, 비상장사, 해외 법인은 일부 누락될 수 있습니다.** 상대 후보는 "
        "나스닥·뉴욕 대형주 정적 목록 + peer 리스트 + 이번 세션 검색 이력으로 한정됩니다.\n"
        "- **지분 투자·보유는 대량 보유(5% 이상) 공시이며, 전략적 투자 의도까지 자동으로 "
        "의미하지는 않습니다.**\n"
        "- **점선은 최신 뉴스 기준 철회·무산된 관계**이고, **화살표는 방향이 공식 근거로 "
        "확인된 관계에만** 표시됩니다 — 나머지는 선만 있습니다.\n"
        "- **근거가 많다고 관계가 더 확실한 건 아닙니다.** 노드 크기는 근거 수와 무관하게 "
        "전부 같습니다."
    )

info = st.session_state.info
hub_name = info.get("longName") or info.get("shortName") or ticker


def _known_companies():
    return list({
        **{kc["ticker"].upper(): kc for kc in STATIC_KNOWN_COMPANIES},
        **{
            p["ticker"].upper(): {"ticker": p["ticker"], "name": p["name"]}
            for p in st.session_state.peer_data["peers"] if p.get("name")
        },
    }.values())


# --- 데이터 수집: 뉴스(이미 세션에 있음) + SEC 4종(공시 내 언급/자회사/지분 보유는 여기서
# 티커별로 캐시) — 하나가 실패해도 나머지는 그대로 표시되도록 각각 독립적으로 캐시한다.
if st.session_state.get("filing_edges_ticker") != ticker:
    known = _known_companies()
    progress = st.progress(0.0, text="SEC 공시자료에서 관계 확인 중(양방향)...")

    def _on_progress(done, total):
        progress.progress(done / total if total else 1.0, text=f"SEC 공시자료에서 관계 확인 중 (양방향)... ({done}/{total})")

    filing_edges = find_filing_relationships(ticker, hub_name, known, on_progress=_on_progress)
    progress.progress(1.0, text="공시 원문에서 계약 문맥 확인 중...")
    filing_edges = attach_context_snippets(filing_edges)
    progress.empty()
    st.session_state.update(filing_edges=filing_edges, filing_edges_ticker=ticker)

if st.session_state.get("subsidiary_edges_ticker") != ticker:
    with st.spinner("Exhibit 21 자회사 목록 확인 중..."):
        subsidiary_edges, subsidiary_truncated = find_subsidiaries(ticker)
    st.session_state.update(
        subsidiary_edges=subsidiary_edges, subsidiary_truncated=subsidiary_truncated,
        subsidiary_edges_ticker=ticker,
    )

if st.session_state.get("ownership_edges_ticker") != ticker:
    with st.spinner("Schedule 13D/13G 대량 지분 보유 확인 중..."):
        ownership_edges = find_beneficial_owners(ticker)
    st.session_state.update(ownership_edges=ownership_edges, ownership_edges_ticker=ticker)

news_edges = st.session_state.get("relationship_edges", [])
filing_edges_result = st.session_state.get("filing_edges", [])
subsidiary_edges = st.session_state.get("subsidiary_edges", [])
subsidiary_truncated = st.session_state.get("subsidiary_truncated", False)
ownership_edges = st.session_state.get("ownership_edges", [])
all_edges = news_edges + filing_edges_result + subsidiary_edges + ownership_edges

if not all_edges:
    st.info(
        "관계도를 그릴 수 있는 근거가 없습니다 — 아는 회사 목록에 있는 회사가 이 종목의 "
        "뉴스·공시에 언급되지 않았고, 자회사·대량 지분 보유 공시도 찾지 못했습니다. "
        "(관계가 없다는 뜻이 아니라, 이 방식으로는 확인되지 않았다는 뜻입니다.)"
    )
    st.stop()


def _date_str(epoch):
    """엣지의 unix timestamp를 YYYY-MM-DD로. 값이 없으면 빈 문자열(0을 1970년으로
    표시해버리면 '오래된 근거'처럼 보이는 오독이 생긴다)."""
    if not epoch:
        return ""
    try:
        return datetime.fromtimestamp(epoch).strftime("%Y-%m-%d")
    except Exception:
        return ""


# _best_description()이 문맥을 하나도 못 찾았을 때 쓰는 안내문 — 이미 한글이라 번역
# 대상에서 제외해야 한다(아래 한글 번역 토글 참고).
_NO_CONTEXT_PLACEHOLDER = "원문 확인 필요 (문맥 추출 안 됨)"


def _best_description(g, max_chars=200):
    """"관계 유형"(전략적 제휴/공시 내 언급 등)만으로는 실제로 뭘 하는 관계인지 알 수
    없어서, 그래프 hover와 근거 원문 표에만 있던 실제 문맥(뉴스 요약 또는 공시 발췌)을
    요약 표의 "핵심 발췌" 컬럼에도 끌어와 한눈에 보이게 한다. 문맥(context)이 있는 근거
    중 최신 것을 우선 채택하고, 문맥을 하나도 못 얻은 공시 내 언급은 헤드라인 자체가
    내용이 없으므로 원문 확인을 안내한다 — 뉴스/자회사/지분 보유 헤드라인은 그 자체로
    내용이 있어 그대로 쓴다.

    lib/sec_filings.py가 문장 경계에서 다듬어 넘겨주므로(최대 320자), 여기서 다시 글자
    수로 뚝 자르면 "단어 중간에서 끊긴다"는 문제가 되풀이된다 — 자를 일이 있어도 단어
    경계(공백)에서 자른다."""
    with_context = [h for h in g["headlines"] if h[4]]
    if with_context:
        text = max(with_context, key=lambda h: h[0])[4]
    else:
        latest = max(g["headlines"], key=lambda h: h[0])
        text = _NO_CONTEXT_PLACEHOLDER if latest[5] == "공시 내 언급" else latest[1]
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0].rstrip(",;:.…") + "…"
    return text


# --- 필터: 관계 유형 / 근거 등급 / 공시 내 언급 포함 / 기간 (작업 지시서 5절) ---------
_CORE_TYPES = ["자회사", "지분 투자·보유", "M&A", "공급·고객 계약", "전략적 제휴", "합작투자", "라이선싱"]
_DEAL_TYPES = {"M&A", "공급·고객 계약", "전략적 제휴", "합작투자", "라이선싱"}
_PERIOD_DAYS = {"최근 12개월": 365, "최근 24개월": 730, "전체": None}

st.subheader("필터")
f_col1, f_col2, f_col3, f_col4 = st.columns([2, 2, 1, 1])
with f_col1:
    selected_types = st.multiselect("관계 유형", _CORE_TYPES, default=_CORE_TYPES)
with f_col2:
    selected_grades = st.multiselect("근거 등급", ["A", "B", "C", "D"], default=["A", "B", "C"])
with f_col3:
    include_mentions = st.toggle("공시 내 언급 포함", value=False)
with f_col4:
    period_choice = st.radio("기간", list(_PERIOD_DAYS.keys()), index=1)

period_days = _PERIOD_DAYS[period_choice]
cutoff_epoch = None
if period_days:
    cutoff_dt = datetime.combine(date.today() - timedelta(days=period_days), datetime.min.time())
    cutoff_epoch = int(cutoff_dt.timestamp())


def _edge_visible(e):
    rel_type = e["relationship_type"]
    grade = e.get("evidence_grade", "D")
    if rel_type == "공시 내 언급":
        return include_mentions and "D" in selected_grades
    if rel_type not in selected_types or grade not in selected_grades:
        return False
    # 자회사는 기간 필터의 영향을 받지 않는다(작업 지시서 5절 — 공시 기준일만 표기).
    if cutoff_epoch and rel_type != "자회사":
        dt = e.get("datetime")
        if dt and dt < cutoff_epoch:
            return False
    return True


visible_edges = [e for e in all_edges if _edge_visible(e)]

if not visible_edges:
    st.info("필터 조건에 맞는 관계가 없습니다 — 관계 유형/근거 등급을 넓히거나 기간을 늘려보세요.")
    st.stop()

grouped = group_relationship_edges(visible_edges)

# --- KPI: 필터와 무관하게 "이 종목에 대해 확보된 근거 전체" 기준(작업 지시서 5절) -------
core_edges_all = [e for e in all_edges if e["relationship_type"] in _CORE_TYPES]


def _cp_key(e):
    return e["counterparty_ticker"] or e["counterparty_name"]


kpi_core_cps = {_cp_key(e) for e in core_edges_all}
kpi_subsidiary_cps = {_cp_key(e) for e in core_edges_all if e["relationship_type"] == "자회사"}
kpi_ownership_count = sum(1 for e in core_edges_all if e["relationship_type"] == "지분 투자·보유")
kpi_deal_count = sum(1 for e in core_edges_all if e["relationship_type"] in _DEAL_TYPES)

kpi1, kpi2, kpi3, kpi4 = st.columns(4)
kpi1.metric("핵심 관계 상대기업", f"{len(kpi_core_cps)}개")
kpi2.metric("자회사", f"{len(kpi_subsidiary_cps)}개")
kpi3.metric("지분 보유", f"{kpi_ownership_count}건")
kpi4.metric("M&A·계약·제휴", f"{kpi_deal_count}건")
if subsidiary_truncated:
    st.caption("자회사 최대 30개까지만 표시합니다 — 전체 목록은 원문 Exhibit 21에서 확인하세요.")

def _looks_like_ticker(s):
    """자회사·13D/13G 보고자는 실제 티커가 없으면 그룹 키가 회사명 전체로 대체된다
    (lib/charts.py::group_relationship_edges) — 그런 "가짜 티커"를 로고·섹터 조회에
    그대로 넘기면 yfinance/Finnhub에 의미 없는 호출만 늘어난다. 진짜 티커처럼 보이는
    것만 걸러서 넘긴다."""
    return bool(re.match(r"^[A-Z]{1,5}(\.[A-Z]{1,2})?$", s or ""))


# 그래프에 상대기업을 상위 몇 개로 자르지 않고 전부 그린다. 로고도 실제 티커가 있는
# 상대기업 + 허브에 대해서만 받는다. Finnhub 무료 티어(분당 60회) 한도에 걸릴 수 있는데,
# 실패한 티커는 조용히 빈 원으로 폴백되므로 최악의 경우도 로고 없는 모습일 뿐 깨지지 않는다.
graph_tickers = [cp for cp, _ in grouped]
ticker_like = [cp for cp in graph_tickers if _looks_like_ticker(cp)]
logo_cache_key = (ticker, tuple(ticker_like))
if st.session_state.get("relationship_logo_key") != logo_cache_key:
    with st.spinner("회사 로고 불러오는 중..."):
        logos = get_circular_logos([ticker] + ticker_like)
    st.session_state.update(relationship_logos=logos, relationship_logo_key=logo_cache_key)

# 상대기업(실제 티커가 있는 것만)이 많을 때만 섹터를 조회해 그래프에서 묶는다 — 회사
# 수가 적으면 한 링에 다 들어가서 묶어도 얻는 게 없고, yfinance 호출도 그만큼 아낀다.
sectors = {}
if len(ticker_like) > SECTOR_CLUSTER_THRESHOLD:
    sector_cache_key = (ticker, tuple(ticker_like))
    if st.session_state.get("relationship_sector_key") != sector_cache_key:
        with st.spinner("섹터 정보 불러오는 중..."):
            sectors = get_sectors(ticker_like)
        st.session_state.update(relationship_sectors=sectors, relationship_sector_key=sector_cache_key)
    else:
        sectors = st.session_state.get("relationship_sectors", {})

st.plotly_chart(
    render_relationship_graph_figure(
        ticker, hub_name, visible_edges,
        logos=st.session_state.get("relationship_logos", {}), sectors=sectors,
    ),
    use_container_width=True, config=RELATIONSHIP_PLOTLY_CONFIG,
)
caption = (
    "노드에 마우스를 올리면 요약이 보입니다. 화살표는 방향이 공식 근거로 확인된 관계에만 "
    "표시됩니다 — 나머지는 선만 있습니다. 전체 근거와 원문 링크는 아래 표에 있습니다."
)
# 섹터가 실제로 2종류 이상 나와야 클러스터링이 눈에 보이는 효과가 있다 — 다 조회했는데
# 전부 못 찾았거나(sectors 값이 죄다 None) 한 섹터뿐이면 "묶어서 배치했다"는 문구가
# 오히려 과장이 된다.
if len({v for v in sectors.values() if v}) > 1:
    caption += " 상대기업이 많아 같은 섹터끼리 묶어서 배치했습니다."
st.caption(caption)

_DIRECTION_LABELS = {
    "outbound": "→ (당사→상대)",
    "inbound": "← (상대→당사)",
    "bidirectional": "↔ 상호",
    "unknown": "미확인",
}

subheader_col, translate_col = st.columns([3, 1])
with subheader_col:
    st.subheader("상대기업별 요약")
with translate_col:
    # "핵심 발췌"는 SEC 공시/뉴스 원문(영어) 그대로라, 옵션 데이터 페이지의 '가격순으로'
    # 토글과 같은 자리에 번역 스위치를 둔다 — 기본은 원문(끄기), 켜면 한글로 바꿔 보여준다.
    # 관계 유형·상태·등급 같은 구조화 필드는 번역하지 않는다(작업 지시서 5절).
    show_korean = st.toggle("한글로 보기")

summary_rows = []
for cp_ticker, g in grouped:
    latest = max(g["headlines"], key=lambda h: h[0])
    summary_rows.append({
        "상대기업": g["name"] or cp_ticker,
        "관계 유형": ", ".join(g["types"]),
        "방향": _DIRECTION_LABELS.get(g["direction"], "미확인"),
        "상태": g["latest_status"] or "",
        "근거 등급": g["best_grade"],
        "지분율": f"{g['ownership_pct']:.1f}%" if g["ownership_pct"] is not None else "",
        "최근 근거일": _date_str(g["latest_dt"]),
        "핵심 발췌": _best_description(g),
        "원문": latest[2] or None,
    })

if show_korean:
    # 이미 한글인 안내문(_NO_CONTEXT_PLACEHOLDER)은 번역기에 넣으면 오히려 깨지므로 제외.
    to_translate = [
        r["핵심 발췌"] for r in summary_rows if r["핵심 발췌"] != _NO_CONTEXT_PLACEHOLDER
    ]
    with st.spinner("한글로 번역 중..."):
        prefetch_korean(to_translate)
    for r in summary_rows:
        if r["핵심 발췌"] != _NO_CONTEXT_PLACEHOLDER:
            r["핵심 발췌"] = to_korean(r["핵심 발췌"])

st.dataframe(
    pd.DataFrame(summary_rows),
    hide_index=True, use_container_width=True,
    column_config={
        "방향": st.column_config.TextColumn(
            "방향", width="small", help="방향이 공식 근거로 확인된 관계만 화살표로 표시합니다.",
        ),
        "근거 등급": st.column_config.TextColumn(
            "근거 등급", width="small",
            help="A: 구조화된 SEC 공식 문서 · B: SEC 문맥 정황 · C: 뉴스 보도 · D: 공시 내 단순 언급",
        ),
        "지분율": st.column_config.TextColumn("지분율", width="small", help="확실히 추출된 경우만 표시합니다."),
        "핵심 발췌": st.column_config.TextColumn(
            "핵심 발췌", width="large",
            help="뉴스 요약 또는 SEC 공시 발췌 — 실제 근거 원문은 아래 표에서 확인하세요.",
        ),
        "원문": st.column_config.LinkColumn("원문", display_text="열기", width="small"),
    },
)
st.caption("⚠️ 근거가 많다고 관계가 더 확실하다는 뜻은 아닙니다 — 등급과 원문을 직접 확인하세요.")

# 근거 전체를 엣지 단위로 — 예전엔 이 정보가 그래프 hover 안에만 있어서 원문으로 바로
# 갈 방법이 없었고(hover에서는 링크를 클릭할 수 없다), 터치 환경에서는 hover 자체가 안 떴다.
st.subheader("근거 원문")
detail_rows = []
for cp_ticker, g in grouped:
    for dt, headline, url, status, context, rel_type, grade, source_kind in sorted(
        g["headlines"], key=lambda h: h[0], reverse=True,
    ):
        detail_rows.append({
            "날짜": _date_str(dt),
            "상대기업": g["name"] or cp_ticker,
            "소스": source_kind or ("SEC 공시" if rel_type == "공시 내 언급" else "뉴스"),
            "관계 유형": rel_type,
            "등급": grade,
            "상태": status or "",
            "발췌 / 헤드라인": context or headline,
            "원문": url or None,
        })
detail_rows.sort(key=lambda r: r["날짜"], reverse=True)

st.dataframe(
    pd.DataFrame(detail_rows),
    hide_index=True, use_container_width=True, height=420,
    column_config={
        "날짜": st.column_config.TextColumn("날짜", width="small"),
        "상대기업": st.column_config.TextColumn("상대기업", width="small"),
        "소스": st.column_config.TextColumn("소스", width="small"),
        "관계 유형": st.column_config.TextColumn("관계 유형", width="small"),
        "등급": st.column_config.TextColumn("등급", width="small"),
        "상태": st.column_config.TextColumn("상태", width="small"),
        "발췌 / 헤드라인": st.column_config.TextColumn("발췌 / 헤드라인", width="large"),
        "원문": st.column_config.LinkColumn("원문", display_text="열기", width="small"),
    },
)
st.caption(
    f"전체 {len(detail_rows)}건. 발췌문은 공시 원문에서 회사명 주변을 그대로 잘라온 것이라 "
    "문장이 중간에서 시작하거나 끝날 수 있습니다 — 맥락이 애매하면 원문을 여세요."
)
