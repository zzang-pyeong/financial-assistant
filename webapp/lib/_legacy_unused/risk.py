def compute_stop_take_profit(entry, ind):
    """부록_손절익절_계산스펙.md 1~2번 공식"""
    atr = ind["atr14"]
    ma20 = ind["ma20"]
    lower = ind["boll_lower"]
    upper = ind["boll_upper"]
    swing_low = ind["swing_low_20"]
    prior_high = ind["prior_high_60"]

    stop_candidates = {
        "ATR×2 기준": entry - atr * 2,
        "20일 스윙로우 기준": swing_low - atr * 0.3,
        "볼린저 하단 기준": lower,
    }
    if ma20 < entry:
        stop_candidates["MA20 기준"] = ma20

    floor = entry - atr * 1
    valid_candidates = {k: v for k, v in stop_candidates.items() if v <= floor} or stop_candidates
    stop_label = max(valid_candidates, key=valid_candidates.get)
    stop = valid_candidates[stop_label]

    tp_candidates = {
        "R:R 1.5 기준": entry + (entry - stop) * 1.5,
        "직전 60일 전고점 기준": prior_high,
        "볼린저 상단 기준": upper,
    }
    tp_label = min(tp_candidates, key=tp_candidates.get)
    take_profit = tp_candidates[tp_label]

    return {
        "stop": stop,
        "stop_label": stop_label,
        "stop_candidates": stop_candidates,
        "take_profit": take_profit,
        "tp_label": tp_label,
        "tp_candidates": tp_candidates,
        "atr": atr,
    }
