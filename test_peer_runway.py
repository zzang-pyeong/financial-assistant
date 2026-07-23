import yfinance as yf

tickers = ["USAR", "MP", "EMAT", "IPX.AX", "CRML", "MTRN", "CMP"]

print(f"{'Ticker':7} {'TotalCash($M)':>14} {'FCF($M/yr)':>12} {'Runway(개월)':>12} {'CurrentR':>9} {'QuickR':>8} {'D/E':>8} {'EV/Rev':>8} {'PBR':>7}")
for tk in tickers:
    info = yf.Ticker(tk).info
    cash = info.get("totalCash")
    fcf = info.get("freeCashflow")
    cr = info.get("currentRatio")
    qr = info.get("quickRatio")
    de = info.get("debtToEquity")
    evrev = info.get("enterpriseToRevenue")
    pbr = info.get("priceToBook")

    if cash is not None and fcf is not None and fcf < 0:
        runway = cash / abs(fcf) * 12
        runway_str = f"{runway:.1f}"
    elif fcf is not None and fcf >= 0:
        runway_str = "흑자(FCF+)"
    else:
        runway_str = "N/A"

    def m(x):
        return f"{x/1e6:.1f}" if isinstance(x, (int, float)) else "·"
    def f2(x):
        return f"{x:.2f}" if isinstance(x, (int, float)) else "·"

    print(f"{tk:7} {m(cash):>14} {m(fcf):>12} {runway_str:>12} {f2(cr):>9} {f2(qr):>8} {f2(de):>8} {f2(evrev):>8} {f2(pbr):>7}")
