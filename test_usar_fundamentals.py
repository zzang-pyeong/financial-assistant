import yfinance as yf

t = yf.Ticker("USAR")
info = t.info

keys = ["shortName", "sector", "industry", "forwardPE", "trailingPE",
        "priceToBook", "returnOnEquity", "debtToEquity", "marketCap"]
for k in keys:
    print(f"{k}: {info.get(k)}")

print("\n--- earnings dates ---")
try:
    cal = t.calendar
    print(cal)
except Exception as e:
    print("calendar error:", e)
