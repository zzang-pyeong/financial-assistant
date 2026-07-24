import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.append(str(Path(__file__).parent.parent))

from lib.glossary import render_glossary
from lib.page_helpers import require_analysis, inject_base_styles, render_wordmark
from lib.search import render_sidebar

st.set_page_config(page_title="Peer List — EnterTicker", layout="wide")
inject_base_styles()
require_analysis()

with st.sidebar:
    render_sidebar()

ticker = st.session_state.ticker
render_wordmark("Peer", "List")
st.caption(ticker)
st.page_link("app.py", label="← Back to Search", icon="🏠")
st.divider()

_BASIS_KO = {
    "same industry": "동일 산업",
    "same sector + cap band": "동일 섹터·시총",
    "niche keyword": "니치 키워드",
    "": "—",
}

peer_data = st.session_state.peer_data
rows = []
for p in sorted(peer_data["peers"], key=lambda x: x["tier"]):
    h = p["health"]
    runway_str = "흑자" if h["fcf_positive"] else (f"{h['runway_months']:.0f}개월" if h["runway_months"] is not None else "·")
    rows.append({
        "Tier": "Tier1" if p["tier"] == 1 else "Tier2",
        "근거": _BASIS_KO.get(p.get("tier_basis", ""), "—"),
        "티커": p["ticker"],
        "기업명": p["name"],
        "Forward PE": round(p["forwardPE"], 1) if isinstance(p["forwardPE"], (int, float)) else None,
        "EV/Revenue": round(h["ev_revenue"], 1) if isinstance(h["ev_revenue"], (int, float)) else None,
        "당좌비율": round(h["quick_ratio"], 2) if isinstance(h["quick_ratio"], (int, float)) else None,
        "현금 런웨이": runway_str,
    })

st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

render_glossary(
    ["Forward PER", "EV/Revenue", "유동비율·당좌비율", "현금 런웨이"],
    title="ℹ️ 지표 설명",
)
