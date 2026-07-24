# 논의용 초안: Peer 비교 지표 확장

> 2026-07-25 작성. **아직 `lib/peers.py`에 반영 안 됨** — 우선순위 확인 후 진행 예정.
> Perplexity 분석에서 제안된 후보 목록에, 실제 티커 5개로 yfinance 채움률을 실측해 추가함.

## 현재 지표 (7개)

Forward PE, EV/Revenue, 당좌비율, PBR, D/E, ROE, 현금런웨이
(`lib/peers.py::get_financial_health`, Peer Compare/List 페이지에 표시 중)

## 실측: 후보 지표의 yfinance 채움률 (NVDA/AMD/USAR/AMKR/IREN, 대형주 2 + 소형·적자주 3)

이 앱이 실제로 자주 다루는 종목군(초기 단계·적자 소형주)에서 특히 중요한 실측 — 옛
PRD에서도 "trailing PE 채움률 2/7, PEG 2/7"로 이익 기반 지표가 무력화됨을 이미 확인한 바 있음.
이번 실측도 같은 패턴을 재확인:

| 지표 | 채움률(5개 중) | 비고 |
|---|---|---|
| Trailing PE | 4/5 | 적자 종목(USAR)만 결측 — Forward PE와 결측 패턴 비슷 |
| PEG Ratio (`pegRatio`) | 4/5 | 위와 동일 |
| PEG Ratio (`trailingPegRatio`) | 2/5 | **`pegRatio` 필드가 훨씬 안정적** — 이 필드는 쓰지 말 것 |
| EV/EBITDA | 5/5 | 적자(EBITDA<0)여도 값은 나옴(예: USAR -22.7) — 단, 음수는 "적자" 별도 표기 필요(숫자만 보면 저평가로 오독 위험) |
| P/S (`priceToSalesTrailing12Months`) | 5/5 | 매우 안정적. 단 이미 있는 EV/Revenue와 개념이 겹침(부채/현금 반영 여부만 다름) — 굳이 둘 다 넣을 가치가 있는지 검토 필요 |
| Operating Margin | 5/5 | 안정적, 적자여도 음수값으로 나와서 유의미 |
| Gross Margin | 5/5 | 안정적 |
| Revenue Growth YoY | 3/5 | USAR 결측, IREN은 0.0(실제 0인지 결측 대체값인지 구분 안 됨 — 검증 필요) |
| EPS Growth | 3/5 | USAR/IREN 결측 — 이익 기반이라 예상대로 소형/적자주에서 약함 |
| Current Ratio | 5/5 | **매우 안정적** — 기존 당좌비율과 병기하기 좋음(재고 포함/제외 버전) |
| Dividend Yield | 2/5 | 배당 안 하는 성장주는 대부분 결측(정상) |
| Payout Ratio | 5/5 | 배당 안 하면 대부분 0으로 채워짐 — dividendYield와 같이 봐야 의미 있음 |

## 우선순위 제안 (실측 기반)

**1순위 (채움률 높고, 기존 지표와 안 겹침)**
- Current Ratio — 당좌비율과 나란히 두면 "재고 포함하면 어떤지"까지 보임, 채움률 5/5
- Operating Margin / Gross Margin — 수익성 프로파일, 적자 여부와 무관하게 항상 유의미한 숫자

**2순위 (채움률 좋지만 해석에 주의 문구 필요)**
- EV/EBITDA — 음수일 때 "적자(EV/EBITDA 무의미)"로 별도 표기해야 오독 방지됨
- Revenue Growth YoY — IREN의 `0.0`이 진짜 0인지 결측 대체값인지 먼저 확인 필요

**3순위 (기존 지표와 겹치거나 소형주에서 약함)**
- P/S — EV/Revenue와 개념 중복, 굳이 둘 다 넣을지는 취향 문제
- Trailing PE / PEG — Forward PE와 결측 패턴이 비슷해서 추가 가치가 크지 않음(둘 다 있으면 "Forward만 있고 Trailing은 없음/그 반대" 케이스 정도만 보완)
- Dividend Yield / Payout Ratio — 이 앱이 주로 다루는 소형·성장주엔 대부분 해당 없음(결측 아니고 "배당 없음"이 맞는 상태라 오히려 정상)

**보류 (yfinance에 안정적 필드 없음, 별도 계산 필요해서 스코프 커짐)**
- P/FCF — `marketCap / freeCashflow` 직접 계산 필요(freeCashflow는 이미 있음, 나눗셈만 하면 됨 — 사실 이건 즉시 가능)
- 이자보상배율(Interest Coverage) — EBIT/이자비용 직접 계산 필요, 안정적 필드 없음
- 자사주매입 여부 — 단순 필드 없음, 과거 발행주식수 추이 비교가 필요해 스코프 넘어감

## 확인이 필요한 사항 (원안 그대로)

1. ~~yfinance에서 어떤 지표가 신뢰성 있게 제공되는지~~ → 위 표로 확인 완료
2. Tier1 표본이 적을 때(n<3) 평균 대신 어떤 표기를 쓸지 (기존 Forward PE와 동일한 처리 방식 유지 예정 — "표본 부족" 캡션)
3. 지표 수가 늘어나면 UI를 expander로 카테고리별(밸류에이션/수익성/재무건전성/주주환원) 분리할지

## 결정 필요

위 우선순위 제안이 맞는지, 1순위(Current Ratio + Operating/Gross Margin)부터 먼저 넣고
나머지는 보류할지 확인 부탁드립니다. 확정되면 `lib/peers.py::get_financial_health()`에 반영.
