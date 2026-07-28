"""lib/financials.py 스모크 테스트 — 실제 yfinance/SEC/Finnhub 데이터로 눈으로 확인.

CapEx 스토리가 뚜렷한 회사(NVDA, MU)와 자산경량형 회사(CRM)를 섞어서:
1) 정량 지표(매출/마진/CapEx/FCF)가 제대로 뽑히는지
2) 최근 기간에 대해 8-K 기반 경영진 코멘트가 있으면/없으면 각각 정직하게 나오는지
   (억지로 채우지 않고, 없으면 빈 리스트 + 뉴스 폴백까지 확인)
를 표로 출력해 육안 확인한다."""
import sys
sys.path.insert(0, "webapp")

from lib._shared_core import data
from lib.page2_only_financials import financials

TICKERS = ["NVDA", "MU", "CRM"]


def fmt_money(v):
    if v is None:
        return "·"
    return f"${v/1e9:,.2f}B"


def fmt_pct(v):
    if v is None:
        return "·"
    return f"{v*100:.1f}%"


for ticker in TICKERS:
    print(f"\n{'=' * 70}\n{ticker}\n{'=' * 70}")

    income_stmt = data.get_yf_income_stmt(ticker)
    cashflow = data.get_yf_cashflow(ticker)

    revenue = financials.revenue_series(income_stmt)
    gross_margin = financials.gross_margin_series(income_stmt)
    op_margin = financials.operating_margin_series(income_stmt)
    net_income = financials.net_income_series(income_stmt)
    capex = financials.capex_series(cashflow)
    ocf = financials.operating_cash_flow_series(cashflow)
    fcf = financials.free_cash_flow_series(cashflow)
    capex_pct = financials.capex_pct_revenue(capex, revenue)

    if not revenue:
        print("  매출 데이터 없음 — income_stmt 자체를 못 가져왔을 가능성")
        continue

    periods = sorted(revenue.keys(), reverse=True)[:4]
    print(f"  {'기간':<12}{'매출':>10}{'매출총이익률':>14}{'영업이익률':>12}{'순이익':>10}"
          f"{'CapEx':>10}{'OCF':>10}{'FCF':>10}{'CapEx/매출':>12}")
    for p in periods:
        pstr = p.strftime("%Y-%m-%d")
        print(
            f"  {pstr:<12}{fmt_money(revenue.get(p)):>10}"
            f"{fmt_pct((gross_margin or {}).get(p)):>14}"
            f"{fmt_pct((op_margin or {}).get(p)):>12}"
            f"{fmt_money((net_income or {}).get(p)):>10}"
            f"{fmt_money((capex or {}).get(p)):>10}"
            f"{fmt_money((ocf or {}).get(p)):>10}"
            f"{fmt_money((fcf or {}).get(p)):>10}"
            f"{fmt_pct((capex_pct or {}).get(p)):>12}"
        )

    if not periods:
        continue
    latest_period = periods[0].date()
    company_name = (data.get_yf_info(ticker) or {}).get("shortName") or ticker
    print(f"\n  경영진 코멘트 탐색 (기준 기간 종료일: {latest_period}, 회사명: {company_name})")
    for metric in ("capex", "revenue"):
        quotes = financials.find_commentary(ticker, company_name, metric, latest_period)
        if not quotes:
            print(f"    [{metric}] 없음 (8-K에서도 뉴스에서도 못 찾음 — 정직한 빈 결과)")
        else:
            for q in quotes:
                print(f"    [{metric}] ({q['source_kind']}, {q['date']}) {q['quote']}")
                print(f"      → {q['url']}")

print("\n완료")
