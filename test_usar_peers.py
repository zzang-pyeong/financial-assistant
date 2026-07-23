import yfinance as yf
import numpy as np

peers = ["MP", "AII.TO", "MTRN", "USAR", "EMAT", "SSMR", "IE", "CMP", "IPX.AX", "CRML", "UAMY"]

rows = []
for tk in peers:
    try:
        info = yf.Ticker(tk).info
        fpe = info.get("forwardPE")
        name = info.get("shortName")
        rows.append((tk, name, fpe))
    except Exception as e:
        rows.append((tk, f"ERROR: {e}", None))

print(f"{'Ticker':8} {'ForwardPE':>10}  Name")
for tk, name, fpe in rows:
    fpe_str = f"{fpe:.1f}" if isinstance(fpe, (int, float)) else "N/A"
    print(f"{tk:8} {fpe_str:>10}  {name}")

valid = [fpe for _, _, fpe in rows if isinstance(fpe, (int, float)) and fpe > 0]
peer_valid = [fpe for tk, _, fpe in rows if tk != "USAR" and isinstance(fpe, (int, float)) and fpe > 0]

usar_fpe = next(fpe for tk, _, fpe in rows if tk == "USAR")
print(f"\nUSAR Forward PE: {usar_fpe:.1f}")
if peer_valid:
    print(f"Peer 평균 (USAR 제외, 유효값 {len(peer_valid)}개): {np.mean(peer_valid):.1f}")
    print(f"Peer 중앙값: {np.median(peer_valid):.1f}")
    print(f"USAR / Peer평균 배수: {usar_fpe/np.mean(peer_valid):.1f}배")
else:
    print("유효한 peer forwardPE 없음")
