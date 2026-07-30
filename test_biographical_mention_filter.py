"""임원·이사 경력 소개 필터 검증 (2026-07-30). Streamlit 없이 lib.sec_filings만 직접
불러, drop_biographical_mentions()가 "회사 간 관계가 아니라 한 사람의 과거 직장 나열"인
공시 언급을 목록에서 통째로 빼는지, 진짜 관계는 그대로 남는지 확인한다.

실측 재현 케이스: AMAT(Applied Materials) 관계도에 SHOP(Shopify)이 "공시 내 언급"으로
잡힌 문제 — 실제 원문은 Shopify 10-K/A 이사 소개란(사용자가 직접 원문을 확인해 발견):
"Prashanth Mahendra-Rajah, age 55, has been a member of our Board of Directors since
June 2024. ... He has also previously served as Division CFO and in other financial
leadership roles at Applied Materials, Visa, and United Technologies." — AMAT와 Shopify
사이엔 아무 관계도 없고, 그저 이사 한 명의 과거 경력에 두 회사 이름이 같이 등장할 뿐이다."""
import sys
sys.path.insert(0, "webapp")

from lib._shared_page2_page8_filings.sec_filings import (
    drop_biographical_mentions, _BIOGRAPHICAL_MENTION_RE,
)

def edge(cp_ticker, cp_name, context=None, dt=1_700_000_000):
    e = {
        "counterparty_ticker": cp_ticker, "counterparty_name": cp_name,
        "relationship_type": "공시 내 언급", "status": "미확인", "evidence_grade": "D",
        "headline": "테스트", "url": "https://example.com", "datetime": dt,
    }
    if context is not None:
        e["context"] = context
    return e

# 1) 실측 재현: Shopify 이사 소개란 원문 그대로. AMAT 관련 엣지가 전부 빠져야 한다 —
#    문맥이 있는 엣지뿐 아니라, 같은 회사의 문맥 없는 다른 날짜 언급도 같이 빠져야 한다
#    (attach_context_snippets는 회사당 1건에만 context를 채우므로).
SHOPIFY_BIO_TEXT = (
    "Prashanth Mahendra-Rajah, age 55, has been a member of our Board of Directors since "
    "June 2024. Mr. Mahendra-Rajah is the Chief Financial Officer at Uber (NYSE). Prior to "
    "joining Uber in November 2023, Mr. Mahendra-Rajah served as Chief Financial Officer of "
    "Analog Devices for 6 years, and further as Chief Financial Officer of WABCO Holdings "
    "Inc. He has also previously served as Division CFO and in other financial leadership "
    "roles at Applied Materials, Visa, and United Technologies."
)
edges = [
    edge("AMAT", "Applied Materials, Inc.", context=SHOPIFY_BIO_TEXT, dt=1_750_000_000),
    edge("AMAT", "Applied Materials, Inc.", dt=1_740_000_000),  # 문맥 없는 다른 날짜 언급
]
result = drop_biographical_mentions(edges)
assert result == [], f"경력 소개 문단인데도 AMAT 엣지가 안 빠짐: {result}"
print("1) 실측 재현(AMAT/Shopify 이사 경력 소개) — 문맥 없는 다른 날짜 언급까지 전부 제외 OK")

# 2) 회귀 확인 — 진짜 공급업체 언급(임원 경력 소개가 아닌)은 그대로 남아야 한다.
legit_edges = [
    edge("INTC", "Intel Corporation", context=(
        "Received a 2026 Intel EPIC Supplier Award for Excellence in Technology Development."
    )),
]
result = drop_biographical_mentions(legit_edges)
assert len(result) == 1, f"진짜 공급업체 언급이 잘못 제외됨: {result}"
print("2) 진짜 관계(Intel 공급업체상)는 그대로 남음 OK (회귀 확인)")

# 3) 문맥이 아예 없는 엣지(상위 N개 밖이라 attach_context_snippets가 못 채운 경우)는
#    판정할 근거가 없으므로 건드리지 않는다 — 과잉 제거 방지.
no_context_edges = [edge("XYZ", "Some Company Inc.")]
result = drop_biographical_mentions(no_context_edges)
assert len(result) == 1, f"문맥 없는 엣지까지 제외됨(과잉 동작): {result}"
print("3) 문맥 없는 엣지는 판정 안 하고 그대로 둠 OK (과잉 제거 방지)")

# 4) 실측 재현 2 — HPE/Dell 케이스(이전에 문장경계 수정으로 잡아낸 문장)도 경력 소개
#    패턴으로 이중으로 걸러지는지 확인(같은 문장이 "previously served"는 아니지만
#    "spent more than a decade in ... leadership roles"로 걸려야 한다).
GOULDEN_TEXT = (
    "Goulden previously spent more than a decade in senior leadership roles at EMC "
    "Corporation, an enterprise technology company acquired by Dell Technologies in 2016, "
    "where he served as Chief Financial Officer, Chief Operating Officer, and Chief "
    "Executive Officer of EMC's Information Infrastructure business."
)
assert _BIOGRAPHICAL_MENTION_RE.search(GOULDEN_TEXT), \
    "HPE/Dell 케이스가 경력 소개 패턴으로 안 걸림(이중 방어 실패)"
print("4) HPE/Dell 케이스도 경력 소개 패턴으로 이중 방어됨 OK")

# 5) 문맥이 여러 개(회사가 여럿) 섞여 있을 때 경력 소개인 회사만 정확히 골라서 빼는지.
mixed_edges = [
    edge("AMAT", "Applied Materials, Inc.", context=SHOPIFY_BIO_TEXT),
    edge("INTC", "Intel Corporation", context=(
        "Received a 2026 Intel EPIC Supplier Award for Excellence in Technology Development."
    )),
]
result = drop_biographical_mentions(mixed_edges)
tickers = {e["counterparty_ticker"] for e in result}
assert tickers == {"INTC"}, f"섞인 목록에서 정확히 골라내지 못함: {tickers}"
print("5) 여러 회사가 섞여 있어도 경력 소개인 회사만 정확히 제외 OK")

print("\n임원·이사 경력 소개 필터 전부 통과")
