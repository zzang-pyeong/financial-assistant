import pandas as pd


def compute_indicators(df):
    """부록_손절익절_계산스펙.md 기준 RSI/MA/볼린저/ATR/MACD 계산"""
    close, high, low = df["Close"], df["High"], df["Low"]

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()

    mid = close.rolling(20).mean()
    std = close.rolling(20).std()
    boll_upper = mid + 2 * std
    boll_lower = mid - 2 * std

    tr = pd.concat(
        [high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1
    ).max(axis=1)
    atr14 = tr.rolling(14).mean()

    # MACD: EMA(12) - EMA(26), 시그널선 = MACD의 EMA(9)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    macd_signal = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = macd_line - macd_signal

    # 골든/데드크로스: "현재 정배열/역배열 상태"가 아니라 "직전 봉 대비 막 교차했는지"를 감지
    ma_diff = ma20 - ma60
    golden_cross = bool(ma_diff.iloc[-1] > 0 and ma_diff.iloc[-2] <= 0)
    dead_cross = bool(ma_diff.iloc[-1] < 0 and ma_diff.iloc[-2] >= 0)

    return {
        "close": close.iloc[-1],
        "rsi": rsi.iloc[-1],
        "ma20": ma20.iloc[-1],
        "ma60": ma60.iloc[-1],
        "boll_upper": boll_upper.iloc[-1],
        "boll_lower": boll_lower.iloc[-1],
        "atr14": atr14.iloc[-1],
        "swing_low_20": low.iloc[-20:].min(),
        "prior_high_60": high.iloc[-60:].max(),
        "macd": macd_line.iloc[-1],
        "macd_signal": macd_signal.iloc[-1],
        "macd_hist": macd_hist.iloc[-1],
        "macd_hist_prev": macd_hist.iloc[-2],
        "golden_cross": golden_cross,
        "dead_cross": dead_cross,
    }


def classify_indicator_signals(ind):
    """각 지표를 bullish/bearish/neutral로 분류 (비대칭 노출용)"""
    signals = []

    rsi = ind["rsi"]
    if rsi < 30:
        signals.append(("RSI(14)", f"{rsi:.1f} — 과매도, 반등 가능성", "bullish"))
    elif rsi > 70:
        signals.append(("RSI(14)", f"{rsi:.1f} — 과매수, 조정 가능성", "bearish"))
    else:
        signals.append(("RSI(14)", f"{rsi:.1f} — 중립 구간", "neutral"))

    close, ma20, ma60 = ind["close"], ind["ma20"], ind["ma60"]
    if ind["golden_cross"]:
        signals.append(("이동평균 골든크로스", f"MA20이 MA60을 방금 상향 돌파 (MA20 {ma20:.2f}, MA60 {ma60:.2f})", "bullish"))
    elif ind["dead_cross"]:
        signals.append(("이동평균 데드크로스", f"MA20이 MA60을 방금 하향 돌파 (MA20 {ma20:.2f}, MA60 {ma60:.2f})", "bearish"))
    elif close > ma20 > ma60:
        signals.append(("이동평균 정배열", f"종가 {close:.2f} > MA20 {ma20:.2f} > MA60 {ma60:.2f}", "bullish"))
    elif close < ma20 < ma60:
        signals.append(("이동평균 역배열", f"종가 {close:.2f} < MA20 {ma20:.2f} < MA60 {ma60:.2f}", "bearish"))
    else:
        signals.append(("이동평균", f"종가 {close:.2f}, MA20 {ma20:.2f}, MA60 {ma60:.2f} — 혼조", "neutral"))

    boll_upper, boll_lower = ind["boll_upper"], ind["boll_lower"]
    if close <= boll_lower:
        signals.append(("볼린저밴드", f"종가가 하단({boll_lower:.2f}) 근처/이탈 — 반등 기대", "bullish"))
    elif close >= boll_upper:
        signals.append(("볼린저밴드", f"종가가 상단({boll_upper:.2f}) 근처/이탈 — 과열 경계", "bearish"))
    else:
        signals.append(("볼린저밴드", f"밴드 중간권 ({boll_lower:.2f}~{boll_upper:.2f})", "neutral"))

    macd_hist, macd_hist_prev = ind["macd_hist"], ind["macd_hist_prev"]
    if macd_hist > 0 and macd_hist_prev <= 0:
        signals.append(("MACD", f"히스토그램 {macd_hist:.2f} — 골든크로스(상승 전환)", "bullish"))
    elif macd_hist < 0 and macd_hist_prev >= 0:
        signals.append(("MACD", f"히스토그램 {macd_hist:.2f} — 데드크로스(하락 전환)", "bearish"))
    elif macd_hist > 0:
        signals.append(("MACD", f"히스토그램 {macd_hist:.2f} — 상승 모멘텀 유지", "bullish"))
    elif macd_hist < 0:
        signals.append(("MACD", f"히스토그램 {macd_hist:.2f} — 하락 모멘텀 유지", "bearish"))
    else:
        signals.append(("MACD", "히스토그램 0 — 중립", "neutral"))

    return signals
