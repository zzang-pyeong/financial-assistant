"""문장 경계 탐지 — 종결부호 뒤 닫는 인용부호 케이스 검증 (2026-07-30). Streamlit 없이
lib.filing_text만 직접 불러 trim_to_sentence()가 '마침표+닫는 인용부호' 뒤에서도 문장을
쪼개는지, 그리고 그 결과가 실제로 제3자 관계 가드(promote_mentions_with_context)의
오탐을 막는지 끝까지 확인한다.

실측 재현 케이스: HPE의 David Goulden 영입 보도자료
(https://www.sec.gov/Archives/edgar/data/1645590/000164559026000072/ex991pressreleasedavidgoul.htm)
— "...continue executing our strategy." Goulden previously...acquired by Dell Technologies in
2016..." 두 문장이 종전 정규식으로는 하나로 묶여, 앞 문장의 "our"가 뒷 문장(HPE와 무관한
2016년 EMC-Dell 인수)의 자기지칭인 것처럼 오인되어 "Dell Technologies"가 M&A 관계로
잘못 승격됐었다."""
import sys
sys.path.insert(0, "webapp")

from lib._shared_page2_page8_filings.filing_text import trim_to_sentence
from lib._shared_page2_page8_filings.sec_filings import promote_mentions_with_context

# 실측 원문 그대로 (SEC 공시에서 직접 확인)
GOULDEN_TEXT = (
    "uniquely positioned to help guide them through this transformation,” said Antonio Neri, "
    "president and CEO of HPE. “We look forward to benefiting from David’s perspectives and "
    "leadership experience as we build on our momentum and continue executing our strategy.” "
    "Goulden previously spent more than a decade in senior leadership roles at EMC Corporation, "
    "an enterprise technology company acquired by Dell Technologies in 2016, where he served as "
    "Chief Financial Officer, Chief Operating Officer, and Chief Executive Officer of EMC's "
    "Information Infrastructure business."
)

# 1) trim_to_sentence가 "Dell Technologies"가 포함된 문장만 골라내고, 앞 문장의 "our"는
#    같이 넘어오면 안 된다.
match_start = GOULDEN_TEXT.find("Dell Technologies")
sentence, start_cut, end_cut = trim_to_sentence(GOULDEN_TEXT, match_start, len("Dell Technologies"))
assert "our" not in sentence.lower(), \
    f"앞 문장('our momentum...')이 같이 묶여서 넘어옴: {sentence}"
assert "Dell Technologies" in sentence, f"정작 매칭 대상이 빠짐: {sentence}"
assert sentence.startswith("Goulden previously"), \
    f"문장 시작 지점이 'strategy.\" ' 뒤에서 안 끊김: {sentence}"
print("1) 종결부호+닫는 인용부호(”) 뒤에서 문장 경계 인식 OK (실측 HPE 보도자료)")
print(f"   → 분리된 문장: {sentence[:70]}...")

# 2) 끝까지 이어서 — 이 스니펫이 실제로 제3자 관계 가드에서 거부되는지(HPE와 무관한
#    2016년 EMC-Dell 인수 얘기이므로 "공시 내 언급"에 그대로 남아야 한다).
edge = {
    "counterparty_ticker": "DELL", "counterparty_name": "Dell Technologies Inc.",
    "relationship_type": "공시 내 언급", "status": "미확인", "evidence_grade": "D",
    "headline": "테스트", "url": "https://example.com", "datetime": 1_700_000_000,
    "context": sentence, "search_direction": "forward",
}
result = promote_mentions_with_context([edge], "Hewlett Packard Enterprise Company")
assert result[0]["relationship_type"] == "공시 내 언급", \
    f"경계 수정 후에도 HPE/Dell이 잘못 승격됨: {result[0]['relationship_type']}"
print("2) 경계 수정 결과 HPE/Dell M&A 오탐 승격 방지 OK (실측 재현 케이스 끝까지 확인)")

# 3) 회귀 확인 — 일반적인 "마침표+공백+대문자" 경계(인용부호 없는 경우)는 여전히 정상
#    동작해야 한다(하위 호환).
plain_text = (
    "In March 2025, the Company entered into a multi-year supply agreement with Taiwan "
    "Semiconductor Manufacturing Company. The agreement covers advanced node capacity through "
    "2027."
)
match_start = plain_text.find("Taiwan Semiconductor")
sentence, _, _ = trim_to_sentence(plain_text, match_start, len("Taiwan Semiconductor"))
assert sentence.startswith("In March 2025") and sentence.endswith("Company."), \
    f"인용부호 없는 일반 경계가 깨짐: {sentence}"
print("3) 인용부호 없는 일반 문장 경계는 기존처럼 정상 동작 OK (회귀 확인)")

# 4) 약어("Inc.") 마침표를 문장 끝으로 오판하지 않는지도 여전히 확인 — 인용부호 케이스를
#    추가해도 이 방어는 안 깨져야 한다.
abbrev_text = "We are a subsidiary of Foo Inc. and operate independently in North America."
match_start = abbrev_text.find("Foo Inc.")
sentence, _, _ = trim_to_sentence(abbrev_text, match_start, len("Foo Inc."))
assert sentence == abbrev_text, f"'Inc.' 뒤에서 문장이 잘못 끊김: {sentence}"
print("4) 'Inc.' 같은 약어 마침표 오판 방지도 여전히 정상 동작 OK (회귀 확인)")

print("\n문장 경계 인용부호 처리 전부 통과")
