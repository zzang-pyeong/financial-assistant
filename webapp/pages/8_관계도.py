import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.append(str(Path(__file__).parent.parent))

from lib.page_helpers import require_analysis, inject_base_styles, render_wordmark
from lib.search import render_sidebar
from lib.charts import (
    render_relationship_graph_figure, group_relationship_edges,
    MAX_RELATIONSHIP_NODES, PLOTLY_CONFIG,
)
from lib.known_companies import STATIC_KNOWN_COMPANIES
from lib.sec_filings import find_filing_relationships, attach_context_snippets
from lib.logos import get_circular_logos

st.set_page_config(page_title="Relationship Map — EnterTicker", layout="wide")
inject_base_styles()
require_analysis()

with st.sidebar:
    render_sidebar()

ticker = st.session_state.ticker
with st.container(key="page_header"):
    render_wordmark("Relationship", "Map", align="center")
    st.caption(ticker)
st.divider()

# 주의사항은 예전엔 6줄짜리 caption 한 덩어리였다 — 길어서 실제로는 아무도 안 읽는 형태였다.
# 한 줄 요약만 항상 보이게 두고, 나머지는 궁금할 때 펼치도록 계층을 나눴다.
st.caption(
    "뉴스와 SEC 공시에 **함께 등장한** 회사들입니다 — 실제 거래관계로 확정된 것이 아니라 "
    "직접 확인해볼 단서입니다."
)
with st.expander("이 화면을 읽을 때 주의할 점"):
    st.markdown(
        "- **목록 밖 회사는 아예 안 나옵니다.** 상대 후보는 나스닥·뉴욕 대형주 정적 목록 + "
        "peer 리스트 + 이번 세션 검색 이력으로 한정됩니다. 정밀 개체명 인식이 아닙니다.\n"
        "- **관계의 방향은 모릅니다.** 누가 인수했고 누가 공급하는지는 판별하지 않습니다 — "
        "두 회사가 같은 문서에 등장했다는 사실까지만 압니다.\n"
        "- **'공시상 언급'은 문맥이 다양합니다.** 실제 계약일 수도 있지만 위험요소 섹션의 "
        "경쟁사 나열, 임원 경력 소개, 소송 상대로 등장한 것일 수도 있습니다. 아래 표의 "
        "발췌문과 원문 링크로 직접 확인하세요.\n"
        "- **점선은 최신 뉴스 기준 철회·무산된 관계**입니다.\n"
        "- **근거가 많다고 관계가 더 확실한 건 아닙니다.** 그래서 노드 크기는 근거 수와 "
        "무관하게 전부 같습니다 — 개수는 아래 표에서 숫자 그대로 보세요."
    )

info = st.session_state.info
hub_name = info.get("longName") or info.get("shortName") or ticker

if st.session_state.get("filing_edges_ticker") != ticker:
    known = list({
        **{kc["ticker"].upper(): kc for kc in STATIC_KNOWN_COMPANIES},
        **{
            p["ticker"].upper(): {"ticker": p["ticker"], "name": p["name"]}
            for p in st.session_state.peer_data["peers"] if p.get("name")
        },
    }.values())
    progress = st.progress(0.0, text="SEC 공시자료에서 관계 확인 중(양방향)...")

    def _on_progress(done, total):
        progress.progress(done / total if total else 1.0, text=f"SEC 공시자료에서 관계 확인 중 (양방향)... ({done}/{total})")

    filing_edges = find_filing_relationships(ticker, hub_name, known, on_progress=_on_progress)
    progress.progress(1.0, text="공시 원문에서 계약 문맥 확인 중...")
    filing_edges = attach_context_snippets(filing_edges)
    progress.empty()
    st.session_state.update(filing_edges=filing_edges, filing_edges_ticker=ticker)

news_edges = st.session_state.get("relationship_edges", [])
filing_edges_result = st.session_state.get("filing_edges", [])
all_edges = news_edges + filing_edges_result


def _date_str(epoch):
    """엣지의 unix timestamp를 YYYY-MM-DD로. 값이 없으면 빈 문자열(0을 1970년으로
    표시해버리면 '오래된 근거'처럼 보이는 오독이 생긴다)."""
    if not epoch:
        return ""
    try:
        return datetime.fromtimestamp(epoch).strftime("%Y-%m-%d")
    except Exception:
        return ""


if not all_edges:
    st.info(
        "관계도를 그릴 수 있는 매칭이 없습니다 — 아는 회사 목록에 있는 회사가 이 종목의 "
        "뉴스·공시에 언급되지 않았습니다. (관계가 없다는 뜻이 아니라, 이 방식으로는 "
        "확인되지 않았다는 뜻입니다.)"
    )
    st.stop()

grouped = group_relationship_edges(all_edges)

kpi1, kpi2, kpi3 = st.columns(3)
kpi1.metric("상대기업", f"{len(grouped)}개")
kpi2.metric("뉴스 근거", f"{len(news_edges)}건")
kpi3.metric("SEC 공시 근거", f"{len(filing_edges_result)}건")

# 로고는 그래프에 실제로 그려지는 노드(상위 N개) + 허브에 대해서만 받는다 — 표에는 안 쓰므로
# 전체 상대기업만큼 받을 이유가 없다. Finnhub 무료 티어(분당 60회)에서 티커당 최대 11회.
# 로고가 없는 회사(특히 소형주)가 흔하고, 그 경우 노드는 로고 도입 전과 똑같이 빈 원이 된다.
graph_tickers = [cp for cp, _ in grouped[:MAX_RELATIONSHIP_NODES]]
logo_cache_key = (ticker, tuple(graph_tickers))
if st.session_state.get("relationship_logo_key") != logo_cache_key:
    with st.spinner("회사 로고 불러오는 중..."):
        logos = get_circular_logos([ticker] + graph_tickers)
    st.session_state.update(relationship_logos=logos, relationship_logo_key=logo_cache_key)

st.plotly_chart(
    render_relationship_graph_figure(
        ticker, hub_name, all_edges, logos=st.session_state.get("relationship_logos", {}),
    ),
    use_container_width=True, config=PLOTLY_CONFIG,
)

# 그래프에 상위 N개만 그리는 건 원래도 그랬는데 화면에 아무 표시가 없어서, 나머지 회사가
# 존재하는지조차 알 수 없었다. 잘린 개수를 명시하고 전체는 아래 표에서 보게 한다.
if len(grouped) > MAX_RELATIONSHIP_NODES:
    st.caption(
        f"그래프에는 근거가 많은 순으로 {MAX_RELATIONSHIP_NODES}개만 그렸습니다 — "
        f"나머지 {len(grouped) - MAX_RELATIONSHIP_NODES}개를 포함한 전체는 아래 표에 있습니다."
    )

st.subheader("상대기업별 요약")
summary_rows = []
for rank, (cp_ticker, g) in enumerate(grouped, start=1):
    latest = max(g["headlines"], key=lambda h: h[0])
    summary_rows.append({
        "그래프": "○" if rank <= MAX_RELATIONSHIP_NODES else "",
        "티커": cp_ticker,
        "기업명": g["name"] or cp_ticker,
        "관계 유형": ", ".join(g["types"]),
        "최신 상태": g["latest_status"] or "",
        "뉴스": g["news_count"],
        "공시": g["filing_count"],
        "최근 근거일": _date_str(g["latest_dt"]),
        "최근 원문": latest[2] or None,
    })

st.dataframe(
    pd.DataFrame(summary_rows),
    hide_index=True, use_container_width=True,
    column_config={
        "그래프": st.column_config.TextColumn("그래프", width="small", help="위 그래프에 노드로 표시된 회사"),
        "뉴스": st.column_config.NumberColumn("뉴스", width="small", help="뉴스 기사에서 잡힌 근거 건수"),
        "공시": st.column_config.NumberColumn("공시", width="small", help="SEC 공시에서 잡힌 근거 건수"),
        "최근 원문": st.column_config.LinkColumn("최근 원문", display_text="열기", width="small"),
    },
)
st.caption("⚠️ 건수는 소스별로 나눠 센 것일 뿐, 많다고 관계가 더 확실하다는 뜻이 아닙니다.")

# 근거 전체를 엣지 단위로 — 예전엔 이 정보가 그래프 hover 안에만 있어서 원문으로 바로
# 갈 방법이 없었고(hover에서는 링크를 클릭할 수 없다), 터치 환경에서는 hover 자체가 안 떴다.
st.subheader("근거 원문")
detail_rows = []
for cp_ticker, g in grouped:
    for dt, headline, url, status, context, rel_type in sorted(
        g["headlines"], key=lambda h: h[0], reverse=True,
    ):
        detail_rows.append({
            "날짜": _date_str(dt),
            "상대기업": cp_ticker,
            "소스": "SEC 공시" if rel_type == "공시상 언급" else "뉴스",
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
        "상태": st.column_config.TextColumn("상태", width="small"),
        "발췌 / 헤드라인": st.column_config.TextColumn("발췌 / 헤드라인", width="large"),
        "원문": st.column_config.LinkColumn("원문", display_text="열기", width="small"),
    },
)
st.caption(
    f"전체 {len(detail_rows)}건. 발췌문은 공시 원문에서 회사명 주변을 그대로 잘라온 것이라 "
    "문장이 중간에서 시작하거나 끝날 수 있습니다 — 맥락이 애매하면 원문을 여세요."
)
