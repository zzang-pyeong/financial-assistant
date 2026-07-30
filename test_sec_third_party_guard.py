"""제3자 관계 가드 검증 (2026-07-30). Streamlit 없이 lib.sec_filings만 직접 불러
promote_mentions_with_context()가 "검색 대상 회사 자신은 등장하지 않는" 문장을
승격시키지 않는지, 반대로 정상적인 자기지칭 문장은 그대로 승격시키는지 확인한다.

실측 재현 케이스: NVDA 관계도에서 AMD가 "전략적 제휴"로 잘못 승격된 문제 — AMD 10-Q
원문(https://www.sec.gov/Archives/edgar/data/2488/000000248826000076/amd-20260328.htm)에서
직접 확인한 실제 문장을 그대로 사용한다."""
import sys
sys.path.insert(0, "webapp")

from lib._shared_page2_page8_filings.sec_filings import (
    promote_mentions_with_context, _self_reference_present,
)

def edge(counterparty_name, context, search_direction):
    return {
        "counterparty_ticker": "AMD", "counterparty_name": counterparty_name,
        "relationship_type": "공시 내 언급", "status": "미확인", "evidence_grade": "D",
        "headline": "테스트", "url": "https://example.com", "datetime": 1_700_000_000,
        "context": context, "search_direction": search_direction,
    }

HUB_NAME = "NVIDIA Corporation"

# 1) 실측 재현: AMD 10-Q Risk Factors에서 그대로 가져온 문장 — "Nvidia가 Intel과 제휴했다"는
#    내용으로, 검색 대상(AMD) 자신은 이 문장에 전혀 등장하지 않는다. 승격되면 안 된다.
third_party_edges = [edge(
    "Advanced Micro Devices, Inc.",
    "For example, in September 2025, Nvidia announced a partnership and investment in "
    "Intel to partner on new data center and client platform products.",
    "reverse",
)]
result = promote_mentions_with_context(third_party_edges, HUB_NAME)
assert result[0]["relationship_type"] == "공시 내 언급", \
    f"제3자(Nvidia-Intel) 문장이 승격됨: {result[0]['relationship_type']}"
print("1) 제3자 관계 문장 승격 거부 OK (실측 AMD/NVDA 재현 케이스)")

# 2) reverse 검색인데 자기지칭 대명사("we")로 상대 회사 자신이 등장하면 정상 승격돼야 한다.
self_ref_pronoun_edges = [edge(
    "Advanced Micro Devices, Inc.",
    "We rely on Nvidia as a sole source supplier for certain graphics components used "
    "in our gaming console products.",
    "reverse",
)]
result = promote_mentions_with_context(self_ref_pronoun_edges, HUB_NAME)
assert result[0]["relationship_type"] != "공시 내 언급", \
    f"자기지칭 대명사가 있는데도 승격 안 됨: {result[0]}"
print(f"2) 자기지칭 대명사('We') 있는 문장은 정상 승격 OK: {result[0]['relationship_type']}")

# 3) reverse 검색인데 대명사 대신 상대 회사 자신의 이름으로 등장해도 승격돼야 한다.
self_ref_name_edges = [edge(
    "Advanced Micro Devices, Inc.",
    "Advanced Micro Devices has entered into a supply agreement with Nvidia for "
    "certain semiconductor components.",
    "reverse",
)]
result = promote_mentions_with_context(self_ref_name_edges, HUB_NAME)
assert result[0]["relationship_type"] != "공시 내 언급", \
    f"자기 회사명이 있는데도 승격 안 됨: {result[0]}"
print(f"3) 자기 회사명 언급된 문장은 정상 승격 OK: {result[0]['relationship_type']}")

# 4) forward 검색(허브 자신의 공시) — 자기지칭 없이 제3자만 등장하면 승격 거부돼야 한다.
forward_third_party_edges = [edge(
    "Foundry Co.",
    "For example, Qualcomm announced a partnership and investment in Foundry Co. to "
    "expand manufacturing capacity.",
    "forward",
)]
result = promote_mentions_with_context(forward_third_party_edges, HUB_NAME)
assert result[0]["relationship_type"] == "공시 내 언급", \
    f"forward 방향 제3자 문장이 승격됨: {result[0]['relationship_type']}"
print("4) forward 방향 제3자 관계 문장도 승격 거부 OK")

# 5) forward 검색 + 허브 자신의 이름으로 등장 — 정상 승격돼야 한다(하위 호환).
forward_self_ref_edges = [edge(
    "Foundry Co.",
    "NVIDIA Corporation has entered into a supply agreement with Foundry Co. to "
    "manufacture advanced chips.",
    "forward",
)]
result = promote_mentions_with_context(forward_self_ref_edges, HUB_NAME)
assert result[0]["relationship_type"] != "공시 내 언급", \
    f"forward 방향 자기 회사명 문장이 승격 안 됨: {result[0]}"
print(f"5) forward 방향 자기 회사명 문장은 정상 승격 OK: {result[0]['relationship_type']}")

# --- 6~9) 실측 재현: AMAT(Applied Materials) 10-K에서 위 가드를 처음 넣었을 때 오히려
# 진짜 관계까지 걸러진 케이스들 — 회사가 정식명("Applied Materials") 대신 축약형
# ("Applied")으로 자기 자신을 부르거나, 매출 비중표처럼 애초에 주어가 없는 문장 형태였다.
AMAT_HUB_NAME = "Applied Materials, Inc."

# 6) 축약형 자기지칭("Applied") — 실제 공급업체상 수상 발표문, Intel과의 진짜 관계.
intc_edges = [edge(
    "Intel Corporation",
    "…EXX team and products will broaden Applied’s portfolio of panel-level advanced "
    "packaging technologies which are designed to enable chipmakers and systems companies to "
    "build larger-body AI accelerators for higher energy-efficient performance. • Received "
    "a 2026 Intel EPIC Supplier Award for Excellence in Technology Development.",
    "forward",
)]
result = promote_mentions_with_context(intc_edges, AMAT_HUB_NAME)
assert result[0]["relationship_type"] != "공시 내 언급", \
    f"실측 AMAT/Intel 공급업체상 문장이 승격 안 됨(축약형 자기지칭 인식 실패): {result[0]}"
print(f"6) 축약형 자기지칭('Applied') 문장 정상 승격 OK (실측 AMAT/Intel): {result[0]['relationship_type']}")

# 7) 축약형 자기지칭 + "and" 병렬 구조 — 실제 Micron과의 DRAM/HBM 공동개발. 이 문장은
#    _DEAL_KEYWORDS_RE에 걸리는 거래 키워드가 없어(가드와 무관하게, 원래도) 승격까지는
#    안 되지만, 적어도 "제3자 관계"로 오인해 가드에서 걸러지면 안 된다 — 가드 함수를
#    직접 테스트한다(승격 여부는 키워드 사전 커버리지 문제라 이 가드의 책임 범위 밖).
mu_context = (
    "Engineers from both companies will work side-by-side at Applied’s EPIC Center to "
    "advance innovation in materials, process integration and 3D advanced packaging as memory "
    "architectures move beyond current production nodes. • Applied and Micron Technology "
    "are working to develop next-generation DRAM, HBM and NAND…"
)
assert _self_reference_present(mu_context, AMAT_HUB_NAME), \
    "실측 AMAT/Micron 문장에서 축약형 자기지칭('Applied')을 인식 못함"
print("7) 축약형 자기지칭 병렬 구조 문장에서 가드가 자기지칭 인식 OK (실측 AMAT/Micron)")

# 8) 매출 비중표 — 주어(자기지칭) 자체가 없는 표 형태지만, 이 표는 정의상 항상 공시 주인
#    자신의 매출 비중이라 자기지칭 없이도 통과해야 한다(승격 자체는 이 표에 거래 키워드가
#    없어 별개 문제라 가드 함수를 직접 테스트한다 — 위 7번과 같은 이유).
tsm_context = (
    "Percentage of Net Revenue Taiwan Semiconductor Manufacturing Company Limited 18 % "
    "Samsung Electronics Co., Ltd. 17 % 26 Table of Contents Item 2."
)
assert _self_reference_present(tsm_context, AMAT_HUB_NAME), \
    "매출 비중표(TSM 18%)가 자기지칭 없다는 이유로 거부됨"
print("8) 매출 비중표는 자기지칭 없이도 가드 통과 OK (실측 AMAT/TSM)")

# 9) 회귀 확인 — 축약형/표 허용을 추가해도, 진짜 제3자(임원 경력 소개) 문장은 여전히
#    거부돼야 한다(실측: AMAT 10-K에 등장하는 이사 경력 소개, Broadcom과 무관).
avgo_edges = [edge(
    "Broadcom Inc.",
    "Prior to that, he held a broad range of leadership positions spanning general management, "
    "engineering, sales, marketing and corporate strategy at companies including Intel, "
    "Broadcom (formerly Avago Technologies Limited) and LSI Corporation.",
    "forward",
)]
result = promote_mentions_with_context(avgo_edges, AMAT_HUB_NAME)
assert result[0]["relationship_type"] == "공시 내 언급", \
    f"임원 경력 소개(AMAT와 무관)가 승격됨: {result[0]['relationship_type']}"
print("9) 축약형/표 허용 추가 후에도 무관한 임원 경력 소개는 여전히 거부 OK (회귀 확인)")

print("\n제3자 관계 가드 전부 통과")
