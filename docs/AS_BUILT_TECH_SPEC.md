# EnterTicker As-Built Technical Specification

> 이 문서는 기획 의도가 아니라 실제 코드(`webapp/`)를 직접 읽고 역으로 작성한 as-built
> 명세다. 날짜별 변경 이력은 `CHANGELOG.md`를 참조하고, 제거된 "정밀 검토" 기능의
> 세부사항은 `docs/archive/precision_review.md`를 참조한다.

---

## 문서 범위

제품의 방향성·목표·비목표는 `PRD.md`에 정리했다. 이 문서는 파일명·함수명·데이터 흐름·
매칭 규칙·오탐 방지·폴백·알려진 기술적 한계처럼, 구현을 다시 손댈 때 필요한 세부사항을
담는다. 대상 시장은 나스닥/NYSE/AMEX 등 미국 상장 주식이다.

---

## 현재 제품 구조

`webapp/app.py`는 검색 화면과 Conflict Board 두 화면만 `st.session_state.step`으로
전환하는 단순한 상태머신이다(과거엔 여기에 8단계 "정밀 검토" 흐름이 더 있었으나 제거됨,
아카이브 문서 참조). `webapp/pages/`의 7개 파일이 Streamlit 멀티페이지로 상세 데이터를
나눠 보여준다. `.streamlit/config.toml`에서 `showSidebarNavigation=false`로 Streamlit
자동 네비를 끄고, `lib/search.py::render_sidebar()`(세션 초기화 링크 + 검색창 + 네비
링크)를 모든 페이지가 공통으로 렌더링한다.

**사이드바 표시 순서는 파일명이 아니라 `lib/search.py`의 `_SIDEBAR_PAGES` 리스트 순서가
결정**한다 — 파일명 숫자와 실제 표시 순서가 다를 수 있다.

---

## 화면 정보 구조

### 랜딩 화면 (`step == "search"`)
`layout="centered"`. 워드마크 "Enter**Ticker**", 검색창+"Enter" 버튼이 둥근 필 형태로
병합된 폼. Enter 키 제출을 지원한다.

### Conflict Board (`step == "compare"`)
`layout="wide"`. 매수 관점/매도 관점 2단 컬럼, 각 컬럼 안에 기술적 근거·이벤트·유동성·
밸류에이션·정성적 근거 4개 서브섹션. 카테고리당 5줄 미리보기 + "더보기" expander. 매수=
파랑/매도=주황 컬럼 헤더로만 방향을 구분하고, 근거 텍스트 자체는 색상으로 유불리를
암시하지 않는다. 실적일이 영업일 기준 0~10일 이내로 임박했을 때만, 유동주식비율 30%
미만일 때만 방향 무관 caption을 노출한다("급한 것만" 원칙). 여기서 흐름이 끝난다 — 더
들어갈 다음 단계가 없다.

### 사이드바 (전 페이지 공통, 티커 조회 후에만 노출)
맨 위에 작은 글씨(0.8rem)·톤다운 회색이다가 hover 시에만 경고색(빨강)으로 바뀌는
"↺ 시작화면으로" 세션 초기화 링크, 그 아래 미니 검색 폼(다른 종목으로 즉시 전환), 그
아래 7개 서브페이지 네비게이션 링크가 있다.

### 서브페이지 7종

| 파일 | 화면 | 핵심 내용 |
|---|---|---|
| `1_차트.py` | Price Chart | 일봉(1M/3M/6M/1Y/전체) 또는 분봉(1분/5분/15분/30분/1시간, 상호 배타적 라디오) 캔들차트 + MA20/MA60 + 거래량. 분봉은 KST로 변환 표시, Yahoo 제약(1분=최근7일 등) 고지 |
| `3_섹터_Peer_비교.py` | Peer Compare | 대상 Forward PE, 니치 키워드 그룹(자동판별), Tier1 평균/중앙값, 재무건전성 expander(EV/Revenue·EV/EBITDA·당좌비율·유동비율·런웨이·PBR·D/E·ROE·영업이익률·매출총이익률·매출성장률 + 서술형 요약 코멘트), 하단에 전체 Peer 목록(Tier1+Tier2) 접이식 |
| `4_소유구조.py` | Ownership Map | 종합 요약표(기관/내부자보유율·기관+내부자 합계·공매도비율·유동주식비율·펀드Passive:Active·내부자매매방향성) + 개별 상세 + 내부자 거래 원본 테이블 |
| `5_애널리스트_뉴스.py` | Analyst News | 최근 60일 뉴스 중 등급/목표가 키워드 매칭분(최대 8건), 한글 번역, 매칭 키워드 표시 |
| `6_기업_이벤트_뉴스.py` | Company Events | M&A·경영진교체·신규계약 키워드 매칭(최대 10건) |
| `7_옵션_데이터.py` | Options Data | 향후 6개월 내 만기별 콜/풋 OI·거래량 합계 + 풋/콜비율, 만기 선택 시 행사가별 상세(거래량 내림차순 정렬) |
| `8_관계도.py` | Relationship Map | M&A/신규계약·파트너십 뉴스 + SEC 공시 기반 관계 그래프 |

각 페이지 상단은 `render_wordmark()` 2단어 타이포그래피 + 티커 캡션 + 뒤로가기 링크를
`st.container(key="page_header")`로 묶어 중앙 정렬하고, 하단/본문에 `lib/glossary.py`
용어 설명을 접이식으로 배치한다.

---

## 기능별 구현 명세

### 티커/기업명 검색 (`lib/search.py`, `lib/data.py::resolve_ticker`)
순수 대문자 티커(`^[A-Z]{1,5}(\.[A-Z]{1,3})?$`)는 그대로 쓰고, 한글이 섞이면
`deep_translator`로 영문 변환 후 Yahoo Finance 검색 API를 호출한다(한글 쿼리는 직접
지원 안 함 — 400 에러로 확인됨). `EQUITY` 타입 중 미국 거래소(NMS/NYQ/NGM/NCM/ASE/
PCX/BATS/PNK)를 우선 채택하고, 없으면 아무 EQUITY, 그것도 없으면 원본을 대문자로
강제 변환해 최후 시도한다.

### 데이터 수집 (`fetch_and_store_ticker`)
FinanceDataReader로 가격 이력을 조회하고, 60거래일 미만이면 검색 자체를 중단한다
(MA60 등 롤링 지표가 NaN이 되는 것을 막는 가드 — QNT 등 최근 IPO 종목으로 실증
확인됨). 이어서
지표 계산 → yfinance info/calendar → QQQ 200일선 대비 시장국면 → peer 분류 →
재무건전성 → 소유구조 → 펀드 active/passive → 내부자거래 → 신호분류 → 뉴스 톤분류
(관련성 게이트 통과분만) → 애널리스트 트렌드 → 뉴스 기반 이벤트 필터링 순으로 진행한다.

### 기술적 지표 (`lib/indicators.py`)
RSI(14), MA20/MA60(직전 봉 대비 교차만 감지, 정배열/역배열과 별개 판정), 볼린저(20,
±2σ, 근접만 텍스트 판정 — %B 수치 자체는 미구현), ATR(14), MACD(EMA12/26, 시그널
EMA9). 각 지표를 bullish/bearish/neutral로 분류해 반환한다.

### Peer 비교 (`lib/peers.py::classify_peers`)
Finnhub `company-peers`로 후보를 확보하고, Tier 판정은 동일 산업(industryKey/
industry) 일치 → 동일 섹터+시총 0.1~10배 밴드 → 니치 키워드(rare_earth/lithium/
uranium/copper 사전, business summary 매칭) 순으로 라벨링하되 판정 자체는 OR(하나만
맞아도 Tier1)이다. Tier1 표본만으로 Forward PE 평균/중앙값을 내고, n<3이면 "표본
부족"으로 표기한다.

재무건전성 지표: EV/Revenue, PBR, ROE(부채비율과 함께 해석), 유동/당좌비율, D/E,
현금런웨이(보유현금÷|연간FCF|×12, FCF≥0이면 "흑자전환"), EV/EBITDA(음수면 "적자
(EBITDA 음수) — 배수 무의미"로 별도 표기 — USAR -19.6배처럼 숫자 그대로 보이면
저평가로 오독할 위험이 실측으로 확인됨), 영업이익률·매출총이익률(적자여도 음수로
유의미하게 표시), 매출성장률(YoY, `format_pct()`가 `-0.0%` 같은 부동소수점 잡음을
0.0%로 정규화 — IREN의 revenueGrowth가 실제로 `-0.0`으로 나와 결측 대체값인지
의심했으나 실제 값으로 확인됨).

재무 건전성 expander 맨 위에는 `financial_characteristics_comment()`가 위 지표들을
성장성→수익성→유동성 순으로 묶은 서술형 문장을 만들어 보여준다. 새로운 판단(저평가/
위험 등)을 만들지 않고 이미 표시 중인 사실만 규칙 기반(LLM 없음)으로 재배열한 것이며,
순서를 고정해 어느 카테고리도 더 강조되지 않게 한다 — "비집계(점수 합산 없음)" 원칙에
대한 의도된 예외로 취급한다.

전체 Peer 목록(Tier1+Tier2 전체 테이블, tier·판정근거·티커·기업명 + 위 지표 전부)은
같은 페이지 하단에 접이식으로 들어있다(과거엔 별도 페이지였으나 같은 데이터를 쓰는
페이지라 통합됨).

### 소유구조 (`lib/ownership.py`)
기관/내부자 보유율, 공매도 비율, 유동주식비율(float/shares outstanding, yfinance에
없으면 총발행주식×(1-내부자보유율)로 근사 계산 후 "(추정치)"로 표기)을 보여준다.

기관(13F 공시)과 내부자(Form 3/4/5 공시)는 서로 다른 신고 제도라 둘을 더해도 100%가
안 된다(실측: NVDA 75.5%, AAPL 68.1%, TSLA 61.5%, USAR 65.5%, AMD 74.5% — 전부
미달). 요약표에 "기관+내부자 합계" 행을 따로 두고, 나머지가 개인 투자자 보유율이 아니라
두 공시 제도 어디에도 안 잡히는 나머지(소규모 리테일·13F 문턱 미만 소형 기관·일부
해외 보유분 등)임을 구간 해석에 명시한다.

펀드 단위 액티브/패시브 분류는 펀드명에 `index/etf/spdr/ishares/s&p/russell/total
market` 등 키워드가 있으면 Passive, 없으면 "Active(추정)"으로 본다 — 법인 단위
매핑은 없어 회사명에 전략이 안 드러나면 매칭에 실패한다.

내부자 매매 방향성은 `Text`에 "Purchase"/"Sale"이 포함된 건만 방향 집계에 쓴다
(주식보상/Award와 옵션행사는 제외, "기타"로만 카운트). 매수주식수 vs 매도주식수
비교로 순매수/순매도를 판정한다.

### 뉴스/정성적 근거 (`lib/qualitative.py`)
뉴스 톤 분류는 키워드 매칭 기반 근사치임을 화면에 반복 고지한다(정밀 감성분석 아님).
관련성 게이트(`is_relevant`)는 Finnhub `related` 필드에 티커가 있거나, 헤드라인+요약에
티커/기업명 식별토큰(접미사 제거, 3자 이상)이 단어경계로 등장해야 통과시킨다. 단어경계
정규식 매칭으로 부분문자열 오탐을 막고, 경영진교체는 직함(ceo/cfo/president/chairman
등)과 변경동사(steps down/resigns/appoints 등)가 둘 다 있어야 매칭한다(단순 언급만으로
오탐 안 되게). 애널리스트 관련 뉴스는 "initiates coverage" 등 구체적 문구로 좁혀
필터한다("coverage" 단독 키워드가 무관 기사를 오매칭시킨 이력 때문).

### 관계도 (`pages/8_관계도.py`, `lib/qualitative.py::match_counterparties`,
`lib/sec_filings.py::find_filing_relationships`)
엣지 소스는 두 갈래다.

**뉴스 기반**: M&A + 신규계약/파트너십 뉴스만 대상으로 한다(경영진교체·경쟁관계는
제외 — 경쟁관계는 Peer Compare가 다룸). 후보 회사명에서 접미사(inc/corp/holdings 등)와
업종 일반명사(technology/semiconductor 등)를 제거한 토큰이 전부(ALL) 헤드라인에 있어야
매칭하거나, 티커 심볼이 원문 그대로 단어경계로 등장하면 매칭한다(3자 미만 티커는 흔한
단어와 겹쳐 제외). 단일 토큰 ANY 매칭은 폐기됐다 — "Micron Technology"의 "technology"
같은 흔한 단어 하나로 무관한 회사가 오매칭된 사례 때문이다.

**SEC 공시 기반**: 일반적 관계 문구를 그대로 검색하면 거의 안 걸린다(공시는 격식체를
씀 — NVDA 최근 2년 "supply agreement" 검색 0건으로 실측 확인). 대신 상대 회사 이름
자체가 대상 기업 공시 본문에 등장하는지를 SEC EDGAR Full-Text Search(무료, 키
불필요)로 검색한다. 법인 접미사만 제거하고 업종 일반명사는 남긴다(뉴스 매칭과 반대 —
"Taiwan Semiconductor"처럼 그 단어가 회사명의 핵심인 경우가 많아서). 검색 대상은
`lib/known_companies.py::STATIC_KNOWN_COMPANIES`(정적 목록, ~100개) + peer 리스트이며,
병렬 조회(`ThreadPoolExecutor(max_workers=5)`) 후 캐시한다. 정밀 관계 유형·방향성은
판단하지 않고 히트가 있으면 "공시상 언급"으로만 표시한다. 이 방식으로 뉴스만 쓸 때
2~3개였던 NVDA의 상대 회사 수가 15개 회사·52개 엣지로 늘었다 — peer도 아니고
뉴스에도 안 잡히던 CoreWeave·Microsoft·Oracle·Alphabet 같은 실제 고객사·파트너
관계가 드러남.

회사명에서 접미사를 뗀 뒤 흔한 영단어만 남는 후보가 있어("Arm"→"at arm's length",
"Apple"→"apple-to-apples" 같은 관용구와 충돌, 무관 회사 공시에서 실제로 오탐 확인됨),
정식 법인명 → 안전한 별칭 → 완전 축약 순으로 검색을 시도하고, 마지막 단계까지 가서야
히트가 나면 "흔한 단어 검색이라 오탐 가능" 경고를 붙인다.

SEC가 요구하는 User-Agent 형식은 까다롭다 — 괄호·URL이 들어간 문자열("EnterTicker
(github.com/...)")은 403으로 막히고, 앱이름+이메일형식 문자열("EnterTicker research
contact@example.com")은 통과한다.

뉴스 엣지와 공시 엣지는 스키마가 같아 하나의 그래프 렌더링 함수
(`render_relationship_graph_figure()`)로 병합 표시된다(한 회사가 둘 다에서 잡히면
노드 하나에 두 근거수준이 함께 표시됨). 시각화는 `networkx` 없이 `math.cos/sin` 원형
배치를 쓴다. 방향성(누가 인수/피인수, 공급/수요)과 정밀 문맥 분류는 하지 않는다.

### 애널리스트 의견 (Finnhub recommendation trends)
최신 기간 strongBuy+buy vs strongSell+sell을 비교해 buy가 sell의 1.5배 초과면
bullish, 반대면 bearish, 아니면 neutral로 분류한다.

### 옵션 데이터 (`lib/data.py`)
오늘부터 185일 이내 만기만 대상으로, 만기별 콜/풋 OI·거래량 합계와 풋/콜 OI 비율(0으로
나누기 방지 — 콜 OI 합계가 0인 만기가 있으면 나눗셈 결과가 object dtype이 되어
`.round(2)`가 TypeError를 던지던 버그가 있었고, `pd.to_numeric(errors="coerce")`로
고쳤다)을 보여준다. 특정 만기 선택 시 행사가별 콜/풋 OI·거래량·IV 테이블은 거래량
(volume) 내림차순으로 정렬한다(지금 이 순간 시장이 실제로 가장 주목하는 포지션을
먼저 보여주려는 의도).

### 번역 (`lib/translate.py`)
`deep_translator.GoogleTranslator`로 뉴스 헤드라인 한글 번역, 한글 검색어 영문 변환을
처리한다. 실패 시 원문 그대로 폴백한다. 비공식 API라 향후 차단될 수 있다.

### 제거된 기능
정밀 검토(반대관점 강제확인 → 손절/익절 자동산출 → 매매일지 기록으로 이어지는 8단계
흐름)와 매매일지 기능은 라이브 앱에서 완전히 제거됐다. 세부 내용과 재도입 방법은
`docs/archive/precision_review.md` 참조.

---

## 데이터 파이프라인

```
[검색 입력] → resolve_ticker() → ticker
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        ▼                           ▼                           ▼
FinanceDataReader           yfinance(.info/.calendar/      Finnhub(peers/
(가격 이력)                  mutualfund_holders/            recommendation/
   │                        insider_transactions/           company-news)
   │                        options)
   ▼
compute_indicators() → classify_indicator_signals()
        │
        ├─ classify_peers() (Finnhub 후보 + yfinance industry/sector/summary)
        ├─ get_financial_health() (yfinance info)
        ├─ get_ownership_summary()/get_fund_level_active_passive()/
        │  get_recent_insider_transactions() (yfinance)
        └─ classify_news_tone()/filter_analyst_related_news()/
           filter_corporate_event_news() (Finnhub news + 관련성 게이트)
        │
        ▼
   st.session_state에 전부 저장 → Conflict Board와 모든 서브페이지가 공유
```

---

## 데이터 소스와 캐시

| 카테고리 | 소스 | 캐시 TTL | 비고 |
|---|---|---|---|
| 가격/차트(일봉) | FinanceDataReader | 1시간 | 2024-01-01~ |
| 가격(분봉) | yfinance | 5분 | 인터벌별 조회가능 기간 제한, KST 변환 |
| 펀더멘털/소유구조/섹터/옵션 | yfinance | 1시간(옵션 30분) | 비공식 스크래핑, 데이터 누락 가능성 |
| Peer 목록/뉴스/애널리스트 의견 | Finnhub | 1시간(뉴스 30분) | 무료 티어, API 키 필요(`.env` 또는 Streamlit Secrets) |
| 기업명→티커 검색 | Yahoo Finance 비공식 검색 API | - | 한글 쿼리 미지원, 번역 후 호출 |
| 뉴스 번역 | deep-translator(Google Translate 비공식) | 24시간 | 실패 시 원문 폴백 |
| 관계도 "이미 아는 회사" 목록 | `lib/known_companies.py` 정적 하드코딩(~100개) | - | 새 API 아님, 코드에 박아둔 스냅샷 |
| SEC EDGAR | 관계도 공시 검색 전용 | 24시간 | Full-Text Search API, 무료·키 불필요. 재무제표 소스로는 안 씀(여전히 yfinance) |

---

## 오류 처리 및 폴백

대부분의 데이터 수집 함수는 `try/except`로 실패 시 `None`/`{}`/`[]`를 반환해 한
소스의 실패가 전체 화면을 막지 않게 한다. 가격 이력이 60거래일 미만이면 검색 자체를
막는다(지표 계산 불가). 유동주식비율은 yfinance에 값이 없으면 근사 계산 후 "(추정치)"로
표기한다. 옵션 데이터의 풋/콜 비율 계산은 0으로 나누는 경우를 `pd.to_numeric
(errors="coerce")`로 처리해 NaN으로 남긴다. 번역 실패 시 원문을 그대로 보여준다.

---

## 알려진 한계와 기술 리스크

| 항목 | 상태 |
|---|---|
| 데이터 신선도 타임스탬프 표시 | 없음(캐시 TTL은 있으나 화면 미노출) |
| 투자 조언 아님 고지 | 어디에도 없음 |
| 소스 실패 시 부분 실패 허용 | 있음 |

- 정밀 검토·매매일지 제거로 사용자 행동을 로깅할 수단이 지금은 전혀 없다 — Conflict
  Board 조회 자체를 포함해 어떤 행동도 기록되지 않는다.
- 뉴스 관련성 게이트가 완전하지 않다 — 여러 티커를 묶은 기사가 게이트를 통과해 무관한
  종목에 노출될 수 있다(NVDA 검색 시 Tesla/Rivian/Lucid 기사가 노출된 사례로 실측
  확인). LLM 기반 분류로 정밀도를 높이는 방향은 비용 문제로 보류 중이다. Finnhub
  기반 Forward PER 데이터도 비공식 스크래핑이라 소형주 등에서 누락·부정확할 수 있다.
- 액티브/패시브 펀드 분류는 펀드명 키워드 매칭뿐이라 법인 단위(대형 운용사) 매핑이 없다.
- 볼린저 %B는 미구현 — 근접 여부 텍스트 판정만 있다.
- 락업 해제일 데이터가 없다 — 공식 API에 필드가 없음.
- 전체화면 사이드바 중복 버그 리포트가 있으나 재현에 실패해 원인 미확정.
- 관계도 커버리지는 정적 "이미 아는 회사" 목록 크기에 종속된다 — 목록 밖 회사는 실제로
  관계가 언급돼도 그래프에 나타나지 않는다(재현율을 정확도·무비용과 맞바꾼 의도된 설계).
- 관계도는 관계의 방향성과 정밀한 유형을 모른다 — 두 회사가 같이 언급된다는 것만 안다.
- 관계도 매칭은 회사명에서 업종 일반명사를 뺀 뒤 남는 토큰이 흔한 단어인 경우 잔여
  오탐 위험이 있다. "Block, Inc."(→"block")·"Booking Holdings"(→"booking")·
  "Unity Software"(→"unity")는 이런 이유로 정적 목록에서 실증 전에 아예 제외했다.

---

## 아카이브 기능

정밀 검토(8단계 강제 흐름), 손절/익절 자동산출, 매매일지는 라이브 앱에서 제거됐다.
정밀 검토 코드는 삭제하지 않고 `webapp/archive/precision_review.py`에 보존했으나,
매매일지 저장 모듈과 데이터 파일은 완전히 삭제됐다. 재도입 범위와 절차는
`docs/archive/precision_review.md` 참조.

---

## 관련 문서

- `docs/archive/precision_review.md` — 제거된 정밀 검토 기능의 상세 기록
- `docs/CHANGELOG.md` — 날짜별 변경 이력
- `부록_손절익절_계산스펙.md` — 손절/익절 계산식·파라미터, 삭제된 포지션사이징 기능의 역사
- `데이터소스_조사_나스닥.md` — 데이터 소스 선정 조사
- `relationship_map_design_handoff.md` — 관계도 기능의 "정공법" 설계안(SEC EDGAR/
  Finnhub Supply Chain API/LLM 추출 등). 지금 구현은 스코프를 크게 좁힌 무료 버전이다.
