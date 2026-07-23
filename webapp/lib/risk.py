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


def compute_position_size(
    account,
    risk_pct,
    entry,
    stop,
    earnings_days=None,
    regime_favorable=True,
    earnings_threshold_days=10,
    earnings_multiplier=0.5,
    regime_multiplier=0.6,
):
    """부록 4번 공식: 리스크 기반 역산 + 실적/시장국면 축소 배수"""
    risk_amount = account * risk_pct
    stop_distance = entry - stop
    base_qty = risk_amount / stop_distance if stop_distance > 0 else 0

    multiplier = 1.0
    reasons = []
    if earnings_days is not None and earnings_days <= earnings_threshold_days:
        multiplier *= earnings_multiplier
        reasons.append(f"실적 발표 D-{earnings_days} 임박 → ×{earnings_multiplier}")
    if not regime_favorable:
        multiplier *= regime_multiplier
        reasons.append(f"시장 국면 비우호적(QQQ < MA200) → ×{regime_multiplier}")
    if not reasons:
        reasons.append("축소 조건 해당 없음 (배수 1.0)")

    risk_based_qty = base_qty * multiplier

    # 안전장치: 손절폭이 진입가 대비 매우 작으면(저변동성 고가 종목 등) 리스크 기준
    # 수량이 계좌 자본으로 감당 못 할 만큼 커질 수 있음 — 총 매수금액이 계좌 자본을
    # 넘지 않도록 상한을 둔다 (부록 4.5 참조)
    max_affordable_qty = account / entry if entry > 0 else 0
    capped_by_capital = risk_based_qty > max_affordable_qty
    final_qty = min(risk_based_qty, max_affordable_qty)

    if capped_by_capital:
        reasons.append(
            f"⚠ 계좌 자본 한도로 축소 — 리스크 기준 {risk_based_qty:.1f}주는 "
            f"${risk_based_qty * entry:,.0f} 필요(계좌 ${account:,.0f} 초과) → {max_affordable_qty:.1f}주로 제한"
        )

    return {
        "risk_amount": risk_amount,
        "stop_distance": stop_distance,
        "base_qty": base_qty,
        "multiplier": multiplier,
        "risk_based_qty": risk_based_qty,
        "max_affordable_qty": max_affordable_qty,
        "capped_by_capital": capped_by_capital,
        "final_qty": final_qty,
        "reasons": reasons,
    }
