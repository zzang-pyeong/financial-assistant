import sys
from pathlib import Path

import streamlit as st

sys.path.append(str(Path(__file__).parent.parent))

from lib.page_helpers import require_analysis, inject_base_styles, render_wordmark
from lib.search import render_sidebar
from lib.charts import render_relationship_graph_figure, PLOTLY_CONFIG

st.set_page_config(page_title="Relationship Map — EnterTicker", layout="wide")
inject_base_styles()
require_analysis()

with st.sidebar:
    render_sidebar()

ticker = st.session_state.ticker
render_wordmark("Relationship", "Map")
st.caption(ticker)
st.page_link("app.py", label="← Back to Search", icon="🏠")
st.divider()

st.caption(
    "⚠️ 이미 아는 회사(나스닥·뉴욕 대형주 정적 목록 + peer 리스트 + 이전 검색 이력)가 "
    "M&A·신규 계약/파트너십 헤드라인에 등장하는 경우만 표시 — 정밀 개체명 인식이 아니며, "
    "이 목록 밖의 회사는 그래프에 나타나지 않습니다. 점선은 최신 헤드라인 기준 철회·무산된 "
    "관계입니다. 노드에 마우스를 올리면 세부 유형·진행상태·근거(전부 뉴스 보도 기반, 공식 "
    "확인 아님)를 볼 수 있습니다."
)
relationship_edges = st.session_state.get("relationship_edges", [])
if relationship_edges:
    info = st.session_state.info
    hub_name = info.get("longName") or info.get("shortName") or ticker
    st.plotly_chart(
        render_relationship_graph_figure(ticker, hub_name, relationship_edges),
        use_container_width=True, config=PLOTLY_CONFIG,
    )
else:
    st.caption("관계도를 그릴 수 있는 매칭 없음 (아는 회사 목록에 있는 회사가 뉴스에 언급되지 않음)")
