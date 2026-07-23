import numpy as np
from .data import get_finnhub_peers, get_business_summary, get_yf_info

# 부록 9.3 — 재무 건전성 판정 기준
RUNWAY_RISK_MONTHS = 6
RUNWAY_CAUTION_MONTHS = 12
QUICK_RATIO_RISK = 0.5
QUICK_RATIO_GOOD = 1.0

# 부록 5.2 기본 키워드 사전 (섹터별로 확장 가능)
DEFAULT_KEYWORD_DICTS = {
    "rare_earth": [
        "rare earth", "neodymium", "praseodymium", "dysprosium", "terbium",
        "ndfeb", "heavy rare earth", "light rare earth", "hree", "lree",
    ],
    "lithium": ["lithium", "spodumene", "brine lithium", "lithium carbonate", "lithium hydroxide"],
    "uranium": ["uranium", "u3o8", "enrichment", "nuclear fuel"],
    "copper": ["copper", "porphyry copper", "cathode copper"],
}


def get_financial_health(ticker):
    """부록 9번 — PER이 무력화되는 적자 섹터에서 쓸 보완 지표.
    현금 런웨이 = 보유현금 ÷ |연간 FCF 소진액| × 12개월. FCF>=0이면 '흑자 전환'."""
    info = get_yf_info(ticker)
    cash = info.get("totalCash")
    fcf = info.get("freeCashflow")

    fcf_positive = isinstance(fcf, (int, float)) and fcf >= 0
    runway_months = None
    if isinstance(cash, (int, float)) and isinstance(fcf, (int, float)) and fcf < 0:
        runway_months = cash / abs(fcf) * 12

    return {
        "ev_revenue": info.get("enterpriseToRevenue"),
        "pbr": info.get("priceToBook"),
        "roe": info.get("returnOnEquity"),
        "current_ratio": info.get("currentRatio"),
        "quick_ratio": info.get("quickRatio"),
        "debt_to_equity": info.get("debtToEquity"),
        "fcf_positive": fcf_positive,
        "runway_months": runway_months,
    }


def runway_interpretation(health):
    if health["fcf_positive"]:
        return "흑자 전환 — 소진 우려 없음 (단, 일회성 여부 별도 확인 필요)"
    months = health["runway_months"]
    if months is None:
        return "데이터 부족"
    if months < RUNWAY_RISK_MONTHS:
        return f"위험 — {months:.1f}개월, 단기 증자/희석 가능성"
    if months < RUNWAY_CAUTION_MONTHS:
        return f"주의 — {months:.1f}개월"
    return f"여유 — {months:.1f}개월"


def roe_interpretation(roe, debt_to_equity):
    """ROE는 부채가 많아도 높게 나올 수 있어 부채비율과 함께 봐야 함"""
    if not isinstance(roe, (int, float)):
        return "데이터 없음 (적자 등으로 계산 불가할 수 있음)"
    high_leverage = isinstance(debt_to_equity, (int, float)) and debt_to_equity > 100
    if roe < 0:
        return f"{roe*100:.1f}% — 적자, 자기자본 대비 손실 중"
    if roe > 30 and high_leverage:
        return f"{roe*100:.1f}% — 높지만 부채비율({debt_to_equity:.0f})도 높아 레버리지 효과일 가능성"
    if roe > 15:
        return f"{roe*100:.1f}% — 양호"
    return f"{roe*100:.1f}% — 보통"


def quick_ratio_interpretation(quick_ratio):
    if not isinstance(quick_ratio, (int, float)):
        return "데이터 없음"
    if quick_ratio < QUICK_RATIO_RISK:
        return "위험 — 단기 채무 대비 현금성자산 크게 부족"
    if quick_ratio < QUICK_RATIO_GOOD:
        return "주의"
    return "양호"


def auto_detect_keywords(target_summary):
    """대상 종목 설명에 어떤 기본 사전이 매칭되는지 자동 판별"""
    for name, kws in DEFAULT_KEYWORD_DICTS.items():
        if any(kw in target_summary for kw in kws):
            return name, kws
    return None, []


def classify_peers(ticker, extra_keywords=None):
    peers = [p for p in get_finnhub_peers(ticker) if p != ticker]
    target_summary = get_business_summary(ticker)

    dict_name, keywords = auto_detect_keywords(target_summary)
    if extra_keywords:
        keywords = list(set(keywords + extra_keywords))

    target_matches = [kw for kw in keywords if kw in target_summary]

    results = []
    for p in peers:
        summary = get_business_summary(p)
        info = get_yf_info(p)
        matches = [kw for kw in target_matches if kw in summary]
        tier = 1 if matches else 2
        results.append(
            {
                "ticker": p,
                "name": info.get("shortName"),
                "tier": tier,
                "matches": matches,
                "forwardPE": info.get("forwardPE"),
                "health": get_financial_health(p),
            }
        )
    return {
        "dict_name": dict_name,
        "target_matches": target_matches,
        "peers": results,
    }


def tier1_stats(peer_results, min_sample=3):
    tier1_valid = [
        r for r in peer_results
        if r["tier"] == 1 and isinstance(r["forwardPE"], (int, float)) and r["forwardPE"] > 0
    ]
    if not tier1_valid:
        return None
    values = [r["forwardPE"] for r in tier1_valid]
    return {
        "n": len(values),
        "mean": float(np.mean(values)),
        "median": float(np.median(values)),
        "values": values,
        "tickers": [r["ticker"] for r in tier1_valid],
        "reliable": len(values) >= min_sample,
    }
