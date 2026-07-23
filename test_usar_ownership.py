import yfinance as yf
import pandas as pd
pd.set_option("display.max_columns", None)
pd.set_option("display.width", 200)

t = yf.Ticker("USAR")
info = t.info

keys = ["heldPercentInstitutions", "heldPercentInsiders", "floatShares",
        "sharesOutstanding", "sharesShort", "shortPercentOfFloat"]
print("--- info 필드 ---")
for k in keys:
    print(f"{k}: {info.get(k)}")

print("\n--- 주요 기관 보유자 (institutional_holders) ---")
try:
    ih = t.institutional_holders
    print(ih)
except Exception as e:
    print("error:", e)

print("\n--- 주요 펀드 보유자 (mutualfund_holders) ---")
try:
    mh = t.mutualfund_holders
    print(mh)
except Exception as e:
    print("error:", e)
