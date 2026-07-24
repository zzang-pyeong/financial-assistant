from .data import (
    get_yf_info,
    get_mutualfund_holders,
    get_insider_transactions,
)

PASSIVE_KEYWORDS = [
    "index", "etf", "spdr", "ishares", "s&p", "russell",
    "total market", "extended market", "total stock market",
]


def classify_fund_name(name):
    name_l = (name or "").lower()
    if any(kw in name_l for kw in PASSIVE_KEYWORDS):
        return "Passive"
    return "Active(추정)"


def get_ownership_summary(ticker):
    info = get_yf_info(ticker)
    float_shares = info.get("floatShares")
    shares_out = info.get("sharesOutstanding")
    return {
        "institutions_pct": info.get("heldPercentInstitutions"),
        "insiders_pct": info.get("heldPercentInsiders"),
        "short_pct_float": info.get("shortPercentOfFloat"),
        "float_shares": float_shares,
        "shares_outstanding": shares_out,
        "float_ratio": (float_shares / shares_out) if float_shares and shares_out else None,
    }


def get_fund_level_active_passive(ticker):
    mh = get_mutualfund_holders(ticker)
    if mh is None or mh.empty:
        return None
    mh = mh.copy()
    mh["Type"] = mh["Holder"].apply(classify_fund_name)
    passive_sum = mh.loc[mh["Type"] == "Passive", "pctHeld"].sum()
    active_sum = mh.loc[mh["Type"] == "Active(추정)", "pctHeld"].sum()
    total = passive_sum + active_sum
    return {
        "table": mh,
        "passive_pct": passive_sum,
        "active_pct": active_sum,
        "passive_ratio": (passive_sum / total) if total > 0 else None,
    }


def get_recent_insider_transactions(ticker):
    """부록 8.8 — 주식보상(Award, Value=0)은 자발적 매매가 아니므로 제외"""
    it = get_insider_transactions(ticker)
    if it is None or it.empty:
        return None
    df = it.copy()
    df = df[~df["Text"].fillna("").str.contains("Award", case=False)]
    return df


def insider_trade_direction(insider_tx_df):
    """부록 8.8 — 정적 보유율(%) 대신 실제 매매 방향(순매수/순매도)을 계산.
    Purchase/Sale 텍스트만 방향 판정에 쓰고, Conversion/Exercise(옵션행사) 등
    자발적 시장 매매가 아닌 거래는 방향 집계에서 제외(참고용 '기타'로만 분류)."""
    if insider_tx_df is None or insider_tx_df.empty:
        return None

    text = insider_tx_df["Text"].fillna("")
    is_buy = text.str.contains("Purchase", case=False)
    is_sell = text.str.contains("Sale", case=False)

    buy_shares = int(insider_tx_df.loc[is_buy, "Shares"].fillna(0).sum())
    sell_shares = int(insider_tx_df.loc[is_sell, "Shares"].fillna(0).sum())
    buy_count = int(is_buy.sum())
    sell_count = int(is_sell.sum())
    other_count = len(insider_tx_df) - buy_count - sell_count

    if buy_count == 0 and sell_count == 0:
        direction = "판단 불가 — 매수/매도 거래 없음(옵션행사 등만 존재)"
    elif buy_shares > sell_shares:
        direction = "순매수"
    elif sell_shares > buy_shares:
        direction = "순매도"
    else:
        direction = "중립(매수·매도 균형)"

    return {
        "direction": direction,
        "buy_shares": buy_shares,
        "sell_shares": sell_shares,
        "buy_count": buy_count,
        "sell_count": sell_count,
        "other_count": other_count,
    }


def float_ratio_interpretation(ratio):
    if ratio is None:
        return "데이터 없음"
    if ratio >= 0.8:
        return "높음 — 대부분 자유거래, 변동성 왜곡 가능성 낮음"
    if ratio >= 0.3:
        return "보통 — 내부자/락업 물량 일부 존재"
    return "저유동주식(Low Float) — 별도 경고. 최근 상장/SPAC합병 등 락업 가능성 체크 필요"


def institution_pct_interpretation(pct):
    if pct is None:
        return "데이터 없음"
    if pct >= 0.9:
        return "90%+ — 유동주식 얇아 소수 기관 동시매도 시 변동성 확대 가능"
    if pct >= 0.7:
        return "70~90% — 대형 우량주에서 흔함, 기관 검증 충분 신호"
    if pct >= 0.4:
        return "40~70% — 중간, 개인/초기투자자 비중도 상당"
    return "30% 미만 — 기관 관심 적음, 정보비대칭·변동성 위험 큰 경우 많음"
