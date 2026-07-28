"""app.py와 pages/ 양쪽에서 같이 쓰는 설정값. 여기 한 곳만 바꾸면 됨."""

ANALYST_NEWS_LOOKBACK_DAYS = 60  # 애널리스트/기업이벤트 관련 뉴스는 더 넓은 기간에서 탐색

# 서브페이지가 표시하는 뉴스 개수 상한 (같은 이유로 페이지와 번역 선반영이 공유)
ANALYST_NEWS_DISPLAY_LIMIT = 8
CORPORATE_EVENT_DISPLAY_LIMIT = 10
