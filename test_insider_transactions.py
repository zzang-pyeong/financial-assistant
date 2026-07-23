import yfinance as yf
import pandas as pd
pd.set_option("display.max_columns", None)
pd.set_option("display.width", 200)

for tk in ["USAR", "EMAT", "SSMR"]:
    print(f"\n=== {tk} insider_transactions ===")
    try:
        t = yf.Ticker(tk)
        it = t.insider_transactions
        if it is not None and not it.empty:
            print(it.head(10))
        else:
            print("데이터 없음")
    except Exception as e:
        print("error:", e)

    print(f"--- {tk} calendar (IPO/락업 관련 필드 확인) ---")
    try:
        info = yf.Ticker(tk).info
        print("firstTradeDateEpochUtc / ipoExpectedDate 등:",
              info.get("firstTradeDateMilliseconds"), info.get("ipoExpectedDate"))
    except Exception as e:
        print("error:", e)
