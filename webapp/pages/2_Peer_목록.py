import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.append(str(Path(__file__).parent.parent))

from lib.glossary import render_glossary
from lib.page_helpers import require_analysis

st.set_page_config(page_title="Peer 목록 — Devil's Advocate", layout="wide")
require_analysis()

ticker = st.session_state.ticker
st.title(f"📋 {ticker} — Peer 목록")
st.caption("병치만 하고 점수화하지 않습니다 (원칙 B) — 의사결정 흐름과 분리된 참고용 큰 화면 뷰입니다.")
st.page_link("app.py", label="← 메인 흐름으로 돌아가기", icon="🏠")
st.divider()

peer_data = st.session_state.peer_data
rows = []
for p in sorted(peer_data["peers"], key=lambda x: x["tier"]):
    h = p["health"]
    runway_str = "흑자" if h["fcf_positive"] else (f"{h['runway_months']:.0f}개월" if h["runway_months"] is not None else "·")
    rows.append({
        "Tier": "Tier1" if p["tier"] == 1 else "Tier2",
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
