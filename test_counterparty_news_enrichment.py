"""상대회사 뉴스 enrichment 검증 (2026-07-30). Streamlit 없이 lib.qualitative만 직접
불러, find_counterparty_context_news()가 화면에 표시될 summary까지 검증하는지, 강화된
시황요약 필터가 "tumble/plunge/..." 같은 하락 동사도 걸러내는지 확인한다.

실측 재현 케이스: NVDA 관계도의 AMD 행에 "[상대사 보도] Chip Stocks Tumble as SK hynix
Miss Overshadows AI Demand Strength"처럼 NVDA와 무관한 시황 요약이 근거처럼 뜬 문제 —
표시되는 필드(summary)가 검증 대상(headline)과 다를 수 있다는 게 원인이었다."""
import sys
sys.path.insert(0, "webapp")

import lib._shared_core.qualitative as qualitative

HUB_NAME = "NVIDIA Corporation"
HUB_TICKER = "NVDA"


def _with_fake_news(news_list, fn):
    original = qualitative.get_finnhub_company_news
    qualitative.get_finnhub_company_news = lambda *a, **kw: news_list
    try:
        return fn()
    finally:
        qualitative.get_finnhub_company_news = original


# 1) 실측 재현: 헤드라인은 NVDA를 언급해 검증을 통과하지만, 화면에 실제로 뜨는 summary는
#    NVDA와 무관한 반도체 시황 요약이다 — summary까지 검증해야 걸러진다.
mismatched_news = [{
    "headline": "AMD Slides as Nvidia Steals AI Spotlight",
    "summary": "Chip Stocks Tumble as SK hynix Miss Overshadows AI Demand Strength",
    "datetime": 1_700_000_000, "url": "https://example.com/1",
}]
result = _with_fake_news(
    mismatched_news, lambda: qualitative.find_counterparty_context_news(HUB_NAME, HUB_TICKER, "AMD"),
)
assert result is None, f"헤드라인-요약 불일치 기사가 그대로 통과됨: {result}"
print("1) 헤드라인은 통과해도 summary가 허브와 무관하면 제외 OK (실측 AMD/NVDA 재현 케이스)")

# 2) summary 자체가 강화된 시황 요약 패턴("tumble")에 걸리면 제외돼야 한다(헤드라인 매칭과
#    무관하게).
roundup_summary_news = [{
    "headline": "Nvidia and AMD Chip Stocks Tumble on Demand Fears",
    "summary": "Nvidia and AMD Chip Stocks Tumble on Demand Fears",
    "datetime": 1_700_000_000, "url": "https://example.com/2",
}]
result = _with_fake_news(
    roundup_summary_news, lambda: qualitative.find_counterparty_context_news(HUB_NAME, HUB_TICKER, "AMD"),
)
assert result is None, f"'tumble' 시황 요약 헤드라인이 걸러지지 않음: {result}"
print("2) 강화된 시황 동사('tumble') 필터 OK")

# 3) 정상 케이스 — 헤드라인과 summary 둘 다 실제로 NVDA-AMD 관계를 설명하면 그대로 통과.
legit_news = [{
    "headline": "AMD Announces New Partnership Details Involving Nvidia GPUs",
    "summary": "AMD confirmed today that its new data center platform will integrate "
               "Nvidia GPU technology as part of a broader collaboration.",
    "datetime": 1_700_000_000, "url": "https://example.com/3",
}]
result = _with_fake_news(
    legit_news, lambda: qualitative.find_counterparty_context_news(HUB_NAME, HUB_TICKER, "AMD"),
)
assert result is not None and result["url"] == "https://example.com/3", \
    f"정상 관계 기사가 걸러짐: {result}"
print("3) 헤드라인·summary 둘 다 허브를 언급하는 정상 기사는 통과 OK")

# 4) summary가 아예 없는 기사(Finnhub가 종종 빈 문자열을 준다) — 헤드라인만으로 기존처럼
#    통과해야 한다(하위 호환, summary 없다고 무조건 거부하면 재현율이 떨어진다).
no_summary_news = [{
    "headline": "Nvidia Partners With AMD on Joint Data Center Initiative",
    "summary": "",
    "datetime": 1_700_000_000, "url": "https://example.com/4",
}]
result = _with_fake_news(
    no_summary_news, lambda: qualitative.find_counterparty_context_news(HUB_NAME, HUB_TICKER, "AMD"),
)
assert result is not None and result["url"] == "https://example.com/4", \
    f"summary 없는 정상 헤드라인 기사가 걸러짐: {result}"
print("4) summary 없는 기사는 헤드라인만으로 기존처럼 통과 OK (하위 호환)")

print("\n뉴스 enrichment 검증 전부 통과")
