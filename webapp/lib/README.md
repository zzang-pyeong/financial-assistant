# lib/ 폴더 구성

다른 LLM/작업자에게 특정 부분만 맡길 때 이 구분을 참고할 것.

- **`_shared_core/`** — `search.py`(전 페이지 사이드바 허브)가 직접 의존하거나 2개 이상
  페이지가 함께 쓰는 모듈. 여기 파일을 고치면 여러 페이지에 영향이 갈 수 있으므로
  "이 폴더만" 떼어서 맡기면 안 되고, 변경 시 영향받는 페이지를 함께 확인해야 함.
  (charts, config, data, glossary, indicators, known_companies, ownership,
  page_helpers, peers, qualitative, search, translate)

- **`_shared_page2_page8_filings/`** — SEC 공시 텍스트 검색 로직. `page2_only_financials`와
  8번(관계도) 페이지 양쪽에서 쓰임. 둘 중 하나만 맡길 땐 다른 쪽 사용처도 깨지지
  않는지 확인 필요. (sec_filings, filing_text)

- **`page2_only_financials/`** — 2번 재무제표 페이지 전용. 다른 곳에서 import하지
  않으므로 이 폴더만 떼어서 다른 LLM에게 맡겨도 안전함. (financials)

- **`page8_only_relationship/`** — 8번 관계도 페이지 전용. 이 폴더만 떼어서 맡겨도
  안전함. (logos, sectors)

- **`_legacy_unused/`** — 현재 어떤 페이지에서도 쓰이지 않음. `webapp/archive/precision_review.py`
  (비활성 상태, Streamlit 사이드바에 등록 안 됨)에서만 참조. (risk)
