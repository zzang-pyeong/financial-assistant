import yfinance as yf
import pandas as pd
pd.set_option("display.max_columns", None)
pd.set_option("display.width", 200)

t = yf.Ticker("USAR")

# 패시브(인덱스/ETF) 판별 키워드
PASSIVE_KEYWORDS = [
    "index", "etf", "spdr", "ishares", "s&p", "russell",
    "total stock market", "extended market", "total market"
]

def classify(name):
    name_l = name.lower()
    if any(kw in name_l for kw in PASSIVE_KEYWORDS):
        return "Passive"
    return "Active(추정)"

print("=== 기관 보유자 (법인 단위, institutional_holders) ===")
ih = t.institutional_holders.copy()
ih["Type"] = ih["Holder"].apply(classify)
print(ih[["Holder", "pctHeld", "Type"]].to_string(index=False))
print(f"\n[institutional_holders] 합계 pctHeld: {ih['pctHeld'].sum()*100:.2f}%")

print("\n=== 펀드 단위 보유자 (mutualfund_holders) ===")
mh = t.mutualfund_holders.copy()
mh["Type"] = mh["Holder"].apply(classify)
print(mh[["Holder", "pctHeld", "Type"]].to_string(index=False))

passive_sum = mh.loc[mh["Type"] == "Passive", "pctHeld"].sum()
active_sum = mh.loc[mh["Type"] == "Active(추정)", "pctHeld"].sum()
print(f"\n[mutualfund_holders 기준] Passive 합계: {passive_sum*100:.2f}%")
print(f"[mutualfund_holders 기준] Active(추정) 합계: {active_sum*100:.2f}%")
print(f"Passive : Active 비율 = {passive_sum/(passive_sum+active_sum)*100:.0f}% : {active_sum/(passive_sum+active_sum)*100:.0f}%")

print("\n⚠ 주의: institutional_holders(법인 전체 13F 합산)와 mutualfund_holders(개별 펀드)는")
print("   서로 다른 레벨의 데이터라 단순 합산 시 중복 계산됨. 이 예제에서는 mutualfund_holders")
print("   (펀드 단위, 명칭이 구체적이라 분류 신뢰도 높음)만으로 액티브/패시브 비율을 계산함.")
