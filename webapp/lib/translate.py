import streamlit as st
from deep_translator import GoogleTranslator


@st.cache_data(ttl=86400, show_spinner=False)
def to_korean(text):
    """영문 뉴스 헤드라인을 한글로 번역. 실패 시 원문 그대로 반환."""
    if not text:
        return text
    try:
        return GoogleTranslator(source="en", target="ko").translate(text)
    except Exception:
        return text


@st.cache_data(ttl=86400, show_spinner=False)
def to_english(text):
    """한글 등으로 입력된 기업명을 영문으로 번역 (티커 검색용). 실패 시 원문 그대로 반환."""
    if not text:
        return text
    try:
        return GoogleTranslator(source="auto", target="en").translate(text)
    except Exception:
        return text
