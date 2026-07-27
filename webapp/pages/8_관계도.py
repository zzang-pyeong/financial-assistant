import sys
from pathlib import Path

import streamlit as st

sys.path.append(str(Path(__file__).parent.parent))

from lib.page_helpers import require_analysis, inject_base_styles, render_wordmark
from lib.search import render_sidebar
from lib.charts import render_relationship_graph_figure, PLOTLY_CONFIG
from lib.known_companies import STATIC_KNOWN_COMPANIES
from lib.sec_filings import find_filing_relationships, attach_context_snippets

st.set_page_config(page_title="Relationship Map — EnterTicker", layout="wide")
inject_base_styles()
require_analysis()

with st.sidebar:
    render_sidebar()

ticker = st.session_state.ticker
with st.container(key="page_header"):
    render_wordmark("Relationship", "Map", align="center")
    st.caption(ticker)
    st.page_link("app.py", label="← Back to Search", icon="🏠")
st.divider()

st.caption(
    "⚠️ 이미 아는 회사(나스닥·뉴욕 대형주 정적 목록 + peer 리스트 + 이전 검색 이력)가 "
    "M&A·신규 계약/파트너십 뉴스 또는 SEC 공시(10-K/10-Q/8-K)에 등장하는 경우만 표시 — "
    "정밀 개체명 인식이 아니며, 이 목록 밖의 회사는 그래프에 나타나지 않습니다. 점선은 "
    "최신 뉴스 기준 철회·무산된 관계입니다. 노드에 마우스를 올리면 세부 유형·진행상태·근거를 "
    "볼 수 있습니다 — 공시상 언급(회색)은 뉴스보다 신뢰도가 높지만, 어떤 문맥으로 언급됐는지는 "
    "링크를 눌러 원문에서 직접 확인해야 합니다(경쟁사 비교·소송 등일 수도 있음)."
)

if st.session_state.get("filing_edges_ticker") != ticker:
    known = list({
        **{kc["ticker"].upper(): kc for kc in STATIC_KNOWN_COMPANIES},
        **{
            p["ticker"].upper(): {"ticker": p["ticker"], "name": p["name"]}
            for p in st.session_state.peer_data["peers"] if p.get("name")
        },
    }.values())
    progress = st.progress(0.0, text="SEC 공시자료에서 관계 확인 중...")

    def _on_progress(done, total):
        progress.progress(done / total if total else 1.0, text=f"SEC 공시자료에서 관계 확인 중... ({done}/{total})")

    filing_edges = find_filing_relationships(ticker, known, on_progress=_on_progress)
    progress.progress(1.0, text="공시 원문에서 계약 문맥 확인 중...")
    filing_edges = attach_context_snippets(filing_edges)
    progress.empty()
    st.session_state.update(filing_edges=filing_edges, filing_edges_ticker=ticker)

all_edges = st.session_state.get("relationship_edges", []) + st.session_state.get("filing_edges", [])
if all_edges:
    info = st.session_state.info
    hub_name = info.get("longName") or info.get("shortName") or ticker
    st.plotly_chart(
        render_relationship_graph_figure(ticker, hub_name, all_edges),
        use_container_width=True, config=PLOTLY_CONFIG,
    )
else:
    st.caption("관계도를 그릴 수 있는 매칭 없음 (아는 회사 목록에 있는 회사가 뉴스·공시에 언급되지 않음)")
