import FinanceDataReader as fdr
import pandas as pd
import numpy as np

df = fdr.DataReader('USAR', '2025-01-01')
close = df['Close']
high = df['High']
low = df['Low']

delta = close.diff()
gain = delta.clip(lower=0).rolling(14).mean()
loss = (-delta.clip(upper=0)).rolling(14).mean()
rs = gain / loss
rsi = 100 - (100 / (1 + rs))

ma20 = close.rolling(20).mean()
ma60 = close.rolling(60).mean()

mid = close.rolling(20).mean()
std = close.rolling(20).std()
upper = mid + 2*std
lower = mid - 2*std

tr = pd.concat([
    high - low,
    (high - close.shift()).abs(),
    (low - close.shift()).abs()
], axis=1).max(axis=1)
atr14 = tr.rolling(14).mean()

latest = df.index[-1]
entry = close.iloc[-1]
print(f"티커: USAR, 최신일자: {latest.date()}")
print(f"종가(진입가 가정): {entry:.2f}")
print(f"RSI(14): {rsi.iloc[-1]:.1f}")
print(f"MA20: {ma20.iloc[-1]:.2f}  MA60: {ma60.iloc[-1]:.2f}")
print(f"볼린저 상단: {upper.iloc[-1]:.2f}  하단: {lower.iloc[-1]:.2f}")
print(f"ATR(14): {atr14.iloc[-1]:.2f}")

swing_low_20 = low.iloc[-20:].min()
prior_high = high.iloc[-60:].max()
print(f"최근20일 스윙로우: {swing_low_20:.2f}")
print(f"최근60일 전고점: {prior_high:.2f}")

atr = atr14.iloc[-1]
S1 = entry - atr*2
S2 = swing_low_20 - atr*0.3
S3 = ma20.iloc[-1] if ma20.iloc[-1] < entry else None
S4 = lower.iloc[-1]
candidates = [x for x in [S1, S2, S3, S4] if x is not None]
stop = max(candidates)
print("\n--- 손절가 후보 (부록 공식) ---")
print(f"S1(ATR*2): {S1:.2f}, S2(스윙로우): {S2:.2f}, S3(MA20): {S3}, S4(볼린저하단): {S4:.2f}")
print(f"손절가 = MAX(후보) = {stop:.2f}")

T1 = entry + (entry - stop)*1.5
T2 = prior_high
T3 = upper.iloc[-1]
conservative_target = min(T1, T2, T3)
print("\n--- 익절가 후보 ---")
print(f"T1(R:R1.5): {T1:.2f}, T2(전고점): {T2:.2f}, T3(볼린저상단): {T3:.2f}")
print(f"보수적 익절가(50%) = MIN(후보) = {conservative_target:.2f}")

risk_pct = 0.01
account = 10000
risk_amount = account * risk_pct
stop_distance = entry - stop
base_qty = risk_amount / stop_distance
print("\n--- 포지션 사이징 ---")
print(f"계좌 ${account}, 리스크 {risk_pct*100:.0f}% = ${risk_amount:.2f}")
print(f"손절폭: ${stop_distance:.2f}")
print(f"기본 매수수량: {base_qty:.1f}주 -> {int(base_qty)}주")
