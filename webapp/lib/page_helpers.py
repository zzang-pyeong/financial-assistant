import streamlit as st


def require_analysis():
    """상세 데이터 하위 페이지: 아직 분석 전이면 메인 페이지로 안내하고 중단."""
    if st.session_state.get("step", 1) < 2 or "peer_data" not in st.session_state:
        st.info("먼저 메인 페이지에서 티커를 분석해주세요.")
        st.page_link("app.py", label="← 메인 페이지로", icon="🏠")
        st.stop()
