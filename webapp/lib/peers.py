import numpy as np
from .data import get_finnhub_peers, get_business_summary, get_yf_info

# 부록 9.3 — 재무 건전성 판정 기준
RUNWAY_RISK_MONTHS = 6
RUNWAY_CAUTION_MONTHS = 12
QUICK_RATIO_RISK = 0.5
QUICK_RATIO_GOOD = 1.0
# 유동비율은 재고까지 포함해 당좌비율보다 자연히 높게 나오므로 기준선을 한 단계 위로 잡음
CURRENT_RATIO_RISK = 1.0
CURRENT_RATIO_GOOD = 1.5

# Peer tier 판정 — 동일 섹터 폴백 시 시가총액 밴드(대상의 0.1~10배)
CAP_BAND_LOW = 0.1
CAP_BAND_HIGH = 10.0

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
        "operating_margin": info.get("operatingMargins"),
        "gross_margin": info.get("grossMargins"),
        "ev_ebitda": info.get("enterpriseToEbitda"),
        "revenue_growth_yoy": info.get("revenueGrowth"),
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


def current_ratio_interpretation(current_ratio):
    """당좌비율과 달리 재고까지 포함한 유동자산 기준 — 재고 비중이 큰 업종에서 당좌비율과
    갈리는 정도를 보면 '재고가 안 팔릴 때의 리스크'를 가늠할 수 있다."""
    if not isinstance(current_ratio, (int, float)):
        return "데이터 없음"
    if current_ratio < CURRENT_RATIO_RISK:
        return "위험 — 단기 채무 대비 유동자산(재고 포함)도 부족"
    if current_ratio < CURRENT_RATIO_GOOD:
        return "주의"
    return "양호"


def format_pct(value, decimals=1):
    """비율(fraction)을 퍼센트 문자열로 변환. None/비수치는 None 반환(호출부에서 N/A 처리).
    -0.0 같은 부동소수점 잡음은 0.0으로 정규화(실측: IREN의 revenueGrowth가 -0.0으로 나옴 —
    결측이 아니라 '거의 변화 없음'을 뜻하는 실제 값이라 -0.0% 로 보이는 걸 방지)."""
    if not isinstance(value, (int, float)):
        return None
    pct = round(value * 100, decimals)
    return f"{0.0 if pct == 0 else pct:.{decimals}f}%"


def ev_ebitda_interpretation(ev_ebitda):
    """EBITDA가 음수(적자)면 배수 자체가 의미를 잃어 숫자만 보면 저평가로 오독할 위험이
    커서(실측: USAR -19.6배), 배수 대신 명시적으로 '적자' 문구를 반환한다."""
    if not isinstance(ev_ebitda, (int, float)):
        return "N/A"
    if ev_ebitda < 0:
        return "적자(EBITDA 음수) — 배수 무의미"
    return f"{ev_ebitda:.1f}배"


def auto_detect_keywords(target_summary):
    """대상 종목 설명에 어떤 기본 사전이 매칭되는지 자동 판별"""
    for name, kws in DEFAULT_KEYWORD_DICTS.items():
        if any(kw in target_summary for kw in kws):
            return name, kws
    return None, []


def _norm(value):
    """산업·섹터 문자열을 대소문자/공백 차이 없이 비교하기 위한 정규화. None → ''."""
    return (value or "").strip().lower()


def _within_cap_band(target_cap, peer_cap, low=CAP_BAND_LOW, high=CAP_BAND_HIGH):
    """시가총액이 대상의 low×~high× 범위 안인지. 결측/비수치/0 이하면 False(보수적)."""
    if not isinstance(target_cap, (int, float)) or not isinstance(peer_cap, (int, float)):
        return False
    if target_cap <= 0 or peer_cap <= 0:
        return False
    return low <= (peer_cap / target_cap) <= high


def _classify_one(t_sector, t_industry, t_cap, p_sector, p_industry, p_cap, matches):
    """(tier, tier_basis) 반환. 우선순위 라벨: 동일 산업 > 동일 섹터+시총밴드 > 니치 키워드.
    tier 자체는 OR(순서 무관), 라벨만 우선순위."""
    if t_industry and p_industry and t_industry == p_industry:
        return 1, "same industry"
    if t_sector and p_sector and t_sector == p_sector and _within_cap_band(t_cap, p_cap):
        return 1, "same sector + cap band"
    if matches:
        return 1, "niche keyword"
    return 2, ""


def classify_peers(ticker, extra_keywords=None):
    peers = [p for p in get_finnhub_peers(ticker) if p != ticker]
    target_summary = get_business_summary(ticker)
    target_info = get_yf_info(ticker)

    # 산업/섹터는 정규화 slug(industryKey/sectorKey) 우선, 없으면 표시 문자열 폴백
    t_sector = _norm(target_info.get("sectorKey") or target_info.get("sector"))
    t_industry = _norm(target_info.get("industryKey") or target_info.get("industry"))
    t_cap = target_info.get("marketCap")

    dict_name, keywords = auto_detect_keywords(target_summary)
    if extra_keywords:
        keywords = list(set(keywords + extra_keywords))

    target_matches = [kw for kw in keywords if kw in target_summary]

    results = []
    for p in peers:
        summary = get_business_summary(p)
        info = get_yf_info(p)
        matches = [kw for kw in target_matches if kw in summary]

        p_sector = _norm(info.get("sectorKey") or info.get("sector"))
        p_industry = _norm(info.get("industryKey") or info.get("industry"))
        p_cap = info.get("marketCap")

        tier, tier_basis = _classify_one(
            t_sector, t_industry, t_cap, p_sector, p_industry, p_cap, matches,
        )
        results.append(
            {
                "ticker": p,
                "name": info.get("shortName"),
                "tier": tier,
                "tier_basis": tier_basis,  # 신규(추가만) — 기존 소비자에 무해
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
