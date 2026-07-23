import yfinance as yf

peers = ["MP", "AII.TO", "MTRN", "EMAT", "SSMR", "IE", "CMP", "IPX.AX", "CRML", "UAMY"]
target = "USAR"

# 희토류 관련 키워드 사전 (제품에서는 자동 추출하되, 여기선 검증용으로 수동 정의)
KEYWORDS = [
    "rare earth", "neodymium", "praseodymium", "dysprosium", "terbium",
    "ndfeb", "ree ", "heavy rare earth", "light rare earth", "hree", "lree"
]

def get_summary(tk):
    try:
        info = yf.Ticker(tk).info
        return info.get("longBusinessSummary", "") or ""
    except Exception as e:
        return ""

def matched_keywords(text, keywords):
    text_lower = text.lower()
    return [kw for kw in keywords if kw in text_lower]

target_summary = get_summary(target)
target_matches = matched_keywords(target_summary, KEYWORDS)
print(f"[TARGET] {target} 키워드 매칭: {target_matches}")
print(f"설명 앞부분: {target_summary[:150]}...\n")

print(f"{'Ticker':8} {'Tier':10} 매칭 키워드")
for tk in peers:
    summary = get_summary(tk)
    matches = matched_keywords(summary, KEYWORDS)
    tier = "Tier1(진짜동종)" if matches else "Tier2(광의후보)"
    print(f"{tk:8} {tier:16} {matches}")
