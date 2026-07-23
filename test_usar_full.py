import FinanceDataReader as fdr
import yfinance as yf
from datetime import date
import numpy as np

TODAY = date(2026, 7, 23)

# 1. 실적 발표 임박 체크
t = yf.Ticker("USAR")
cal = t.calendar
earnings_date = cal['Earnings Date'][0]
business_days = np.busday_count(TODAY, earnings_date)
print(f"오늘: {TODAY}, 실적 발표일: {earnings_date}")
print(f"영업일 기준 D-{business_days}")
earnings_multiplier = 0.5 if business_days <= 10 else 1.0
print(f"실적 임박 배수: {earnings_multiplier} ({'적용됨' if earnings_multiplier < 1 else '해당없음'})")

# 2. 시장 국면 필터 (QQQ vs MA200)
qqq = fdr.DataReader('QQQ', '2024-01-01')
qqq_close = qqq['Close']
qqq_ma200 = qqq_close.rolling(200).mean()
qqq_price = qqq_close.iloc[-1]
qqq_ma = qqq_ma200.iloc[-1]
regime_favorable = qqq_price > qqq_ma
regime_multiplier = 1.0 if regime_favorable else 0.6
print(f"\nQQQ 현재가: {qqq_price:.2f}, MA200: {qqq_ma:.2f}")
print(f"시장 국면: {'우호적' if regime_favorable else '비우호적'}")
print(f"시장국면 배수: {regime_multiplier}")

# 3. 최종 포지션 사이징 반영
account = 10000
risk_pct = 0.01
entry = 15.82
stop = 14.43
risk_amount = account * risk_pct
base_qty = risk_amount / (entry - stop)
final_qty = base_qty * earnings_multiplier * regime_multiplier
print(f"\n기본 매수수량: {base_qty:.1f}주")
print(f"최종 매수수량 (배수 적용): {final_qty:.1f}주 -> {int(final_qty)}주")

# 4. 포워드 PER 참고 (peer 비교는 Finnhub API 키 필요해 보류)
info = t.info
print(f"\nUSAR 포워드 PER: {info.get('forwardPE')}")
print(f"섹터: {info.get('sector')} / 업종: {info.get('industry')}")
print("(동종 peer 비교는 Finnhub API 키 발급 후 별도 테스트 필요)")
