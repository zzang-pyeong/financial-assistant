"""app.py와 pages/ 양쪽에서 같이 쓰는 설정값. 여기 한 곳만 바꾸면 됨."""

NEWS_LOOKBACK_DAYS = 56  # 8주 — 정성적 근거(뉴스 톤) 조회 기간
ANALYST_NEWS_LOOKBACK_DAYS = 60  # 애널리스트/기업이벤트 관련 뉴스는 더 넓은 기간에서 탐색

# Conflict Board 정성적 근거에 표시할 뉴스 개수 상한. 헤드라인 1건당 번역 1회라서
# 화면 표시 개수와 번역 선반영(lib/translate.py::prefetch_korean) 대상 개수가 반드시
# 같아야 한다 — 어긋나면 렌더 중에 캐시 미스가 나서 화면이 멈춘다. 그래서 app.py와
# lib/search.py가 각자 숫자를 들고 있지 않고 이 상수 하나를 공유한다.
BOARD_NEWS_LIMIT = 30

# 서브페이지가 표시하는 뉴스 개수 상한 (같은 이유로 페이지와 번역 선반영이 공유)
ANALYST_NEWS_DISPLAY_LIMIT = 8
CORPORATE_EVENT_DISPLAY_LIMIT = 10
