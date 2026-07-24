"""정성적 근거: 뉴스 톤(키워드 기반 근사치) + 애널리스트 투자의견 집계.

⚠️ 뉴스 톤 분류는 정밀 감성분석 모델이 아니라 키워드 매칭 기반 근사치입니다.
   (PRD 6.1 "뉴스/정성" 항목 — 정식 NLP 모델은 별도 개발 과제로 남아있음)

단, 매칭은 단어 경계(word-boundary) 기준이라 부분문자열 오탐은 제거됨
   (예: "cut"이 exe*cut*ive에, "miss"가 co*mmiss*ion에, "win"이 s*win*g에 더 이상 걸리지 않음).
그리고 기사가 실제로 해당 종목에 관한 것인지 관련성 게이트로 1차 필터링함.
"""

import re

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

# 긍정어이지만 뒤에 붙는 맥락이 실제로는 부정인 문구 — 긍정 카운트에서 제외
_POSITIVE_NEGATION_PHRASES = [
    "raises concern", "raises concerns", "raise concern", "raise concerns",
    "raises question", "raises questions", "raises doubt", "raises doubts",
    "raises red flag", "raises red flags", "raises fear", "raises fears",
    "raises risk", "raises risks", "raises alarm", "raises alarms",
]


def _kw_pattern(kw):
    """키워드를 단어 경계 정규식으로. 끝에 '*'가 있으면 어간(접두) 매칭."""
    kw = kw.strip()
    if kw.endswith("*"):
        return r"\b" + re.escape(kw[:-1]) + r"\w*"
    return r"\b" + re.escape(kw) + r"\b"


def _matched_keywords(text, keywords):
    """text에서 단어 경계 기준으로 매칭되는 키워드만 반환(부분문자열 오탐 방지)."""
    text = (text or "").lower()
    return [kw.strip().rstrip("*") for kw in keywords if re.search(_kw_pattern(kw), text)]


# ---------------------------------------------------------------------------
# 관련성 게이트 — 기사가 실제로 해당 종목에 관한 것인지 1차 판정
# ---------------------------------------------------------------------------
_NAME_SUFFIXES = {
    "inc", "incorporated", "corp", "corporation", "co", "ltd", "limited", "plc",
    "holdings", "holding", "group", "the", "class", "common", "stock", "company",
    "sa", "nv", "ag", "llc", "lp", "trust",
}


def _company_tokens(company_name):
    """기업명에서 접미사/불용어를 뺀 식별력 있는 토큰(길이 3+)만."""
    toks = re.findall(r"[a-z0-9]+", (company_name or "").lower())
    return [t for t in toks if len(t) >= 3 and t not in _NAME_SUFFIXES]


def is_relevant(article, ticker, company_name):
    """기사가 해당 종목에 관한 것인지 근사 판정.
    ticker/company_name이 모두 비면 게이트를 적용하지 않음(하위호환)."""
    if not ticker and not company_name:
        return True
    # 1) Finnhub related 필드에 티커가 있으면 관련
    related = article.get("related") or ""
    if ticker and ticker.upper() in [r.strip().upper() for r in related.split(",") if r.strip()]:
        return True
    # 2) 헤드라인+요약에 티커/기업명 식별토큰이 단어 경계로 등장하면 관련
    text = ((article.get("headline") or "") + " " + (article.get("summary") or "")).lower()
    if ticker and re.search(r"\b" + re.escape(ticker.lower()) + r"\b", text):
        return True
    return any(re.search(r"\b" + re.escape(tok) + r"\b", text) for tok in _company_tokens(company_name))


def classify_news_tone(news_list, ticker=None, company_name=None):
    """각 뉴스 헤드라인을 단어경계 키워드 매칭으로 bullish/bearish/neutral 근사 분류.
    관련성 게이트를 통과한(해당 종목에 관한) 기사만 반환."""
    results = []
    for n in news_list:
        if not is_relevant(n, ticker, company_name):
            continue
        headline = (n.get("headline") or "").lower()
        pos_hits = _matched_keywords(headline, POSITIVE_KEYWORDS)
        neg_hits = _matched_keywords(headline, NEGATIVE_KEYWORDS)

        # "raises concerns" 같은 부정 맥락이면 raises/raised를 긍정에서 제외
        if any(p in headline for p in _POSITIVE_NEGATION_PHRASES):
            pos_hits = [kw for kw in pos_hits if kw not in ("raises", "raised", "raise")]

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


def filter_analyst_related_news(news_list, ticker=None, company_name=None):
    """애널리스트 등급/목표가 관련 언급이 있는(그리고 해당 종목에 관한) 뉴스만 근사 필터링.
    ⚠️ 이 뉴스들이 실제 매수/매도 의견 집계(recommendation trends)의
    '진짜 근거'라고 확정할 수 없음 — 관련 있어 보이는 뉴스일 뿐."""
    results = []
    for n in news_list:
        if not is_relevant(n, ticker, company_name):
            continue
        headline = (n.get("headline") or "").lower()
        matched = _matched_keywords(headline, ANALYST_ACTION_KEYWORDS)
        if matched:
            results.append({
                "headline": n.get("headline"),
                "source": n.get("source"),
                "datetime": n.get("datetime"),
                "url": n.get("url"),
                "matched": matched,
            })
    return results


# M&A·신규 계약은 단어경계 키워드 매칭. 경영진 교체는 아래 특수 규칙(직함+변경동사) 사용.
CORPORATE_EVENT_KEYWORDS = {
    "인수합병(M&A)": [
        "acquisition", "acquires", "acquired", "to acquire", "merger", "to merge",
        "buyout", "takeover", "divest", "divests", "divested",
    ],
    "신규 계약/파트너십": [
        "partnership", "strategic partnership", "signs deal", "signs agreement",
        "awarded", "wins contract", "contract win", "collaborat*", "joint venture",
        "supply agreement", "licensing deal",
    ],
}
_MGMT_CATEGORY = "경영진 교체"
# 경영진 교체 = (직함) AND (변경 동사)가 함께 있을 때만 — 단순 CEO 언급 오탐 방지
_MGMT_TITLES = [
    "ceo", "cfo", "chief executive", "chief financial officer", "president", "chairman",
]
_MGMT_CHANGE = [
    "steps down", "step down", "resigns", "resign", "resignation", "appoints",
    "appointed", "names new", "new ceo", "new cfo", "succeeds", "succeed",
    "interim", "departs", "departure", "ousted", "retires", "retire",
    "to lead", "hired as", "fired",
]


def _mgmt_change_hits(text):
    """직함과 변경 동사가 둘 다 있을 때만 매칭 키워드 리스트 반환, 아니면 빈 리스트."""
    titles = _matched_keywords(text, _MGMT_TITLES)
    verbs = _matched_keywords(text, _MGMT_CHANGE)
    if titles and verbs:
        return titles + verbs
    return []


def filter_corporate_event_news(news_list, ticker=None, company_name=None):
    """M&A·경영진 교체·신규 계약/파트너십처럼 굵직한(그리고 해당 종목에 관한) 기업 이벤트 뉴스만 근사 필터링.
    ⚠️ 키워드 매칭 기반 근사치 — 정밀 이벤트 추출이 아님."""
    results = []
    for n in news_list:
        if not is_relevant(n, ticker, company_name):
            continue
        headline = (n.get("headline") or "").lower()
        matched_categories = []
        for category, kws in CORPORATE_EVENT_KEYWORDS.items():
            hits = _matched_keywords(headline, kws)
            if hits:
                matched_categories.append({"category": category, "matched": hits})
        mgmt_hits = _mgmt_change_hits(headline)
        if mgmt_hits:
            matched_categories.append({"category": _MGMT_CATEGORY, "matched": mgmt_hits})
        if matched_categories:
            results.append({
                "headline": n.get("headline"),
                "source": n.get("source"),
                "datetime": n.get("datetime"),
                "url": n.get("url"),
                "categories": matched_categories,
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
