import yfinance as yf

tickers = ["USAR", "MP", "EMAT", "IPX.AX", "CRML", "MTRN", "CMP"]

# PER 외에 peer 비교에 쓸 후보 지표들 — 특히 적자기업에도 유효한 것 위주
fields = [
    "trailingPE", "forwardPE", "pegRatio", "trailingPegRatio",
    "priceToBook", "priceToSalesTrailing12Months",
    "enterpriseToRevenue", "enterpriseToEbitda",
    "grossMargins", "operatingMargins", "profitMargins",
    "returnOnEquity", "returnOnAssets",
    "debtToEquity", "currentRatio", "quickRatio",
    "revenueGrowth", "earningsGrowth",
    "marketCap", "totalCash", "totalDebt", "freeCashflow",
]

def fmt(v):
    if v is None:
        return "·"
    if isinstance(v, float):
        return f"{v:.2f}"
    return str(v)

rows = {}
for tk in tickers:
    info = yf.Ticker(tk).info
    rows[tk] = {f: info.get(f) for f in fields}

# 지표별로 몇 개 종목에서 값이 채워지는지 집계
print(f"{'지표':<32}" + "".join(f"{tk:>9}" for tk in tickers) + "   채움/전체")
for f in fields:
    filled = sum(1 for tk in tickers if isinstance(rows[tk][f], (int, float)))
    vals = "".join(f"{fmt(rows[tk][f]):>9}" for tk in tickers)
    print(f"{f:<32}{vals}   {filled}/{len(tickers)}")
