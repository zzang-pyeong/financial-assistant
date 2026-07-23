"""정성적 근거: 뉴스 톤(키워드 기반 근사치) + 애널리스트 투자의견 집계.

⚠️ 뉴스 톤 분류는 정밀 감성분석 모델이 아니라 키워드 매칭 기반 근사치입니다.
   (PRD 6.1 "뉴스/정성" 항목 — 정식 NLP 모델은 별도 개발 과제로 남아있음)
"""

POSITIVE_KEYWORDS = [
    "surge", "beat", "beats", "upgrade", "upgraded", "record", "raises", "raised",
    "wins", "win", "approval", "approved", "growth", "soar", "soars", "rally",
    "outperform", "buy rating", "partnership", "contract award", "expansion",
]
NEGATIVE_KEYWORDS = [
    "miss", "misses", "downgrade", "downgraded", "lawsuit", "recall", "delay",
    "delayed", "cut", "cuts", "plunge", "plunges", "warns", "warning", "loss",
    "losses", "investigation", "sec probe", "dilution", "offering", "bankruptcy",
    "default", "underperform", "sell rating",
]


def classify_news_tone(news_list):
    """각 뉴스 헤드라인을 키워드 매칭으로 bullish/bearish/neutral 근사 분류"""
    results = []
    for n in news_list:
        headline = (n.get("headline") or "").lower()
        pos_hits = [kw for kw in POSITIVE_KEYWORDS if kw in headline]
        neg_hits = [kw for kw in NEGATIVE_KEYWORDS if kw in headline]
        if pos_hits and not neg_hits:
            lean = "bullish"
        elif neg_hits and not pos_hits:
            lean = "bearish"
        else:
            lean = "neutral"
        results.append({
            "headline": n.get("headline"),
            "source": n.get("source"),
            "datetime": n.get("datetime"),
            "url": n.get("url"),
            "lean": lean,
            "matched": pos_hits + neg_hits,
        })
    return results


def news_tone_summary(classified_news):
    bullish = sum(1 for n in classified_news if n["lean"] == "bullish")
    bearish = sum(1 for n in classified_news if n["lean"] == "bearish")
    neutral = sum(1 for n in classified_news if n["lean"] == "neutral")
    return {"bullish": bullish, "bearish": bearish, "neutral": neutral, "total": len(classified_news)}


ANALYST_ACTION_KEYWORDS = [
    "upgrade", "upgraded", "downgrade", "downgraded", "price target",
    "initiates coverage", "initiated coverage", "resumes coverage", "reiterates",
    "reiterated", "maintains buy", "maintains sell", "maintains hold",
    "raises target", "cuts target", "outperform", "underperform", "buy rating",
    "sell rating", "overweight rating", "underweight rating", "analyst rating",
    "price objective",
]
# 제외: "coverage"/"analyst" 단독 키워드 — 실증 테스트에서 "실시간 시황 보도" 같은
# 무관한 뉴스까지 오매칭됨을 확인, 구체적 문구로 좁힘


def filter_analyst_related_news(news_list):
    """애널리스트 등급/목표가 관련 언급이 있는 뉴스만 근사 필터링.
    ⚠️ 이 뉴스들이 실제 매수/매도 의견 집계(recommendation trends)의
    '진짜 근거'라고 확정할 수 없음 — 관련 있어 보이는 뉴스일 뿐."""
    results = []
    for n in news_list:
        headline = (n.get("headline") or "").lower()
        matched = [kw for kw in ANALYST_ACTION_KEYWORDS if kw in headline]
        if matched:
            results.append({
                "headline": n.get("headline"),
                "source": n.get("source"),
                "datetime": n.get("datetime"),
                "url": n.get("url"),
                "matched": matched,
            })
    return results


def classify_analyst_trend(rec_trends):
    """Finnhub recommendation trends의 최신 기간 집계 → bullish/bearish/neutral"""
    if not rec_trends:
        return None
    latest = rec_trends[0]
    buy_side = latest.get("strongBuy", 0) + latest.get("buy", 0)
    sell_side = latest.get("strongSell", 0) + latest.get("sell", 0)
    hold = latest.get("hold", 0)
    total = buy_side + sell_side + hold
    if total == 0:
        return None
    if buy_side > sell_side * 1.5:
        lean = "bullish"
    elif sell_side > buy_side * 1.5:
        lean = "bearish"
    else:
        lean = "neutral"
    return {
        "period": latest.get("period"),
        "strongBuy": latest.get("strongBuy", 0), "buy": latest.get("buy", 0),
        "hold": hold, "sell": latest.get("sell", 0), "strongSell": latest.get("strongSell", 0),
        "total": total, "lean": lean,
    }
