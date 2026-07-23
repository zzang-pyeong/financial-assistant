import yfinance as yf

# CMP/MTRN처럼 "성숙한 대형주" 프로필(유동주식 높음 + 기관 보유 높음)을 보이는지
# 검증할 후보군 - 소재/광업 섹터 위주
tickers = ["NUE", "FCX", "ALB", "NEM", "LIN", "MTRN", "CMP"]

fields = ["shortName", "sector", "industry", "heldPercentInstitutions",
          "heldPercentInsiders", "floatShares", "sharesOutstanding", "marketCap"]

print(f"{'Tkr':6} {'Inst%':>7} {'Insid%':>7} {'Float%':>7} {'MktCap(B)':>10}  Name")
for tk in tickers:
    try:
        info = yf.Ticker(tk).info
        inst = info.get("heldPercentInstitutions")
        insider = info.get("heldPercentInsiders")
        float_sh = info.get("floatShares")
        shares_out = info.get("sharesOutstanding")
        mcap = info.get("marketCap")
        float_ratio = float_sh/shares_out if float_sh and shares_out else None
        def pct(x):
            return f"{x*100:.1f}" if isinstance(x, (int, float)) else "N/A"
        mcap_b = f"{mcap/1e9:.1f}" if mcap else "N/A"
        print(f"{tk:6} {pct(inst):>7} {pct(insider):>7} {pct(float_ratio):>7} {mcap_b:>10}  {info.get('shortName')}")
    except Exception as e:
        print(f"{tk}: ERROR {e}")
