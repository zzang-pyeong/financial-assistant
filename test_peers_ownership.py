import yfinance as yf

tickers = ["USAR", "MP", "AII.TO", "MTRN", "EMAT", "SSMR", "IE", "CMP", "IPX.AX", "CRML", "UAMY"]

fields = ["shortName", "heldPercentInstitutions", "heldPercentInsiders",
          "shortPercentOfFloat", "floatShares", "sharesOutstanding", "forwardPE"]

rows = []
for tk in tickers:
    try:
        info = yf.Ticker(tk).info
        row = {f: info.get(f) for f in fields}
        row["ticker"] = tk
        if row["floatShares"] and row["sharesOutstanding"]:
            row["float_ratio"] = row["floatShares"] / row["sharesOutstanding"]
        else:
            row["float_ratio"] = None
        rows.append(row)
    except Exception as e:
        rows.append({"ticker": tk, "error": str(e)})

print(f"{'Tkr':7} {'Inst%':>7} {'Insid%':>7} {'Short%':>7} {'Float%':>7} {'FwdPE':>9}  Name")
for r in rows:
    def pct(x):
        return f"{x*100:.1f}" if isinstance(x, (int, float)) else "N/A"
    fpe = f"{r.get('forwardPE'):.1f}" if isinstance(r.get('forwardPE'), (int, float)) else "N/A"
    print(f"{r['ticker']:7} {pct(r.get('heldPercentInstitutions')):>7} {pct(r.get('heldPercentInsiders')):>7} "
          f"{pct(r.get('shortPercentOfFloat')):>7} {pct(r.get('float_ratio')):>7} {fpe:>9}  {r.get('shortName')}")
