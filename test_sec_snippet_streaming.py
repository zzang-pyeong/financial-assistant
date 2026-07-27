"""SEC 공시 스니펫 추출의 스트리밍 스캔·문장 다듬기·후보 스코어링 검증 (2026-07-27).

실제 SEC를 호출하지 않고 requests.get을 가짜로 갈아끼워, 6MB짜리 가짜 10-K에서
(1) 매칭 후보를 모을 만큼만 읽고 멈추는지(_CANDIDATE_SCAN_BYTES 상한) — 문서 전체를
    받지는 않지만, 첫 매칭에서 곧바로 멈추던 예전보다는 더 읽는다는 트레이드오프를 반영
(2) 청크 경계에 태그/회사명이 걸쳐도 스니펫이 깨지지 않는지
(3) 언급이 없으면 문서를 다 훑고도 None을 돌려주는지
(4)~(6) 문장 경계에서 다듬는지(단어 중간 절단 방지)
(7) 매칭이 여럿일 때 실제 거래 내용을 설명하는 문장을 고르는지(경쟁사 나열·Risk Factors
    회피) — 첫 매칭이 아니라 점수가 가장 높은 문장을 고르는 게 이번 개선의 핵심
를 확인한다."""
import sys
sys.path.insert(0, "webapp")

from lib import sec_filings

# --- 가짜 10-K 만들기: 앞쪽 200KB 잡동사니 → 계약 문단 → 뒤쪽 6MB 부록 -------------
FILLER_HEAD = "<p>Item 1A. Risk Factors. " + ("Boilerplate language about market conditions. " * 4000) + "</p>"
CONTRACT = (
    "<div><td class='x'>In March 2025, the Company entered into a multi-year supply "
    "agreement with <b>Taiwan Semiconductor Manufacturing Company</b> under which the "
    "foundry will allocate advanced node capacity to the Company&rsquo;s next generation "
    "accelerators.</td></div>"
)
FILLER_TAIL = "<p>" + ("Exhibit index and signature pages. " * 200000) + "</p>"
FAKE_10K = FILLER_HEAD + CONTRACT + FILLER_TAIL
print(f"가짜 10-K 크기: {len(FAKE_10K)/1024/1024:.1f}MB (계약 문단은 앞에서 {FAKE_10K.index('Taiwan')/1024:.0f}KB 지점)")


class FakeResponse:
    """requests의 stream=True 응답 흉내 — 몇 바이트까지 읽혔는지 기록한다."""
    def __init__(self, body):
        self._body = body.encode("utf-8")
        self.encoding = "utf-8"
        self.bytes_read = 0
        self.closed = False

    def iter_content(self, chunk_size=1):
        for i in range(0, len(self._body), chunk_size):
            if self.closed:
                return
            chunk = self._body[i:i + chunk_size]
            self.bytes_read += len(chunk)
            yield chunk

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.closed = True


last_response = {}

def fake_get(url, **kwargs):
    assert kwargs.get("stream") is True, "스트리밍으로 요청하지 않음"
    resp = FakeResponse(FAKE_10K if url != "http://empty" else "<p>nothing relevant here</p>")
    last_response["r"] = resp
    return resp

sec_filings.requests.get = fake_get

# --- 1) 스캔 상한 -----------------------------------------------------------------
# 이 가짜 문서엔 회사명이 딱 한 번만 나오므로, 매칭 후보를 더 모으려고 계속 읽다가
# _CANDIDATE_SCAN_BYTES(약 1.5MB)에서 멈춰야 한다 — 문서 전체(6.9MB)를 받지는 않지만,
# 첫 매칭 지점에서 곧바로 끊던 예전보다는 더 읽는다(여러 후보를 모아야 하니 트레이드오프).
sec_filings._SNIPPET_CACHE.clear()
snippet = sec_filings._extract_context_snippet(
    "http://fake/10k.htm", "Taiwan Semiconductor Manufacturing Company Limited",
)
read_mb = last_response["r"].bytes_read / 1024 / 1024
total_mb = len(FAKE_10K.encode()) / 1024 / 1024
cap_mb = sec_filings._CANDIDATE_SCAN_BYTES / 1024 / 1024
assert snippet, "스니펫을 못 뽑음"
print(f"\n1) 스캔 상한: 전체 {total_mb:.1f}MB 중 {read_mb:.2f}MB만 읽고 중단 "
      f"({read_mb/total_mb*100:.1f}%, 상한 {cap_mb:.1f}MB)")
assert read_mb < total_mb * 0.5, f"문서를 절반 넘게 읽음 — 상한이 안 걸림: {read_mb:.2f}MB"
assert read_mb <= cap_mb + 0.1, f"후보 스캔 상한을 넘겨서 읽음: {read_mb:.2f}MB > {cap_mb:.1f}MB"

# --- 2) 스니펫 품질 ---------------------------------------------------------------
print(f"\n2) 뽑힌 스니펫:\n   {snippet}\n")
assert "<" not in snippet and ">" not in snippet, f"태그가 남아있음: {snippet}"
assert "td class" not in snippet, "청크 경계에서 태그가 반토막 남"
assert "supply agreement" in snippet, "매칭 지점 앞쪽 문맥이 안 잡힘"
assert "accelerators" in snippet, "매칭 지점 뒤쪽 문맥이 안 잡힘"
assert "’" in snippet or "'" in snippet, "HTML 엔티티(&rsquo;)가 안 풀림"
print("   → 태그 제거·엔티티 해제·앞뒤 문맥 확보 전부 OK")

# --- 3) 언급 없는 문서 ------------------------------------------------------------
sec_filings._SNIPPET_CACHE.clear()
assert sec_filings._extract_context_snippet("http://empty", "Nonexistent Corp") is None
print("\n3) 언급 없는 문서 → None 반환 OK")

# --- 4) 캐시 (같은 문서를 두 번 안 받는지) ------------------------------------------
sec_filings._SNIPPET_CACHE.clear()
sec_filings._extract_context_snippet("http://fake/10k.htm", "Taiwan Semiconductor Manufacturing Company Limited")
first = last_response["r"].bytes_read
last_response["r"] = None
sec_filings._extract_context_snippet("http://fake/10k.htm", "Taiwan Semiconductor Manufacturing Company Limited")
assert last_response["r"] is None, "캐시 적중인데 다시 요청함"
print(f"4) 캐시 OK — 두 번째 호출은 네트워크 요청 0회")

# --- 5) 문서 전체 대비 절감폭 -------------------------------------------------------
# ⚠️ 아래 배율은 이 가짜 문서 기준이다. 실제 10-K 본문은 보통 1~2MB대라, 후보 스캔 상한
# (1.5MB)에 걸려도 대부분 문서 전체보다는 적게 읽는다 — 다만 첫 매칭에서 곧바로 멈추던
# 예전(2.7%)보다는 훨씬 많이 읽는다는 게 이번 개선의 트레이드오프다.
ratio = read_mb / total_mb
print(f"\n5) 문서 전체 대비 {ratio*100:.1f}%만 읽음 (전체 대비 절감은 유지, 예전 조기종료보단 더 읽음)")

print("\n전부 통과")

# --- 6) 문장 경계 다듬기 (2026-07-27 추가, 실제 화면 캡처에서 단어 중간 절단 확인됨) --------
# 예전엔 매칭 지점 앞뒤 고정폭(±180자)만 잘라서 "...etermination, the value of..." 처럼
# 단어 중간에서 끊긴 스니펫이 나왔다. _trim_to_sentence가 문장 단위로 다듬는지 확인한다.

# 6a) 문장이 앞뒤로 온전히 들어있으면 잘림 표시 없이 그 문장 그대로 나오는지
text = "Filler before. In 2028, the Company will supply Widget Corp with parts. Filler after."
match_start = text.index("Widget Corp")
sentence, start_cut, end_cut = sec_filings._trim_to_sentence(text, match_start, len("Widget Corp"))
assert sentence == "In 2028, the Company will supply Widget Corp with parts.", f"문장이 안 맞음: {sentence!r}"
assert not start_cut and not end_cut, f"온전한 문장인데 잘림으로 표시됨: {start_cut}, {end_cut}"
print(f"6a) 문장 경계 추출 OK: {sentence!r}")

# 6b) 회사명 앞에 문장 경계가 전혀 없으면(창 시작까지 이어짐) 시작이 잘린 것으로 표시되는지
frag = "no boundary before this point Widget Corp with parts. Filler after."
sentence2, start_cut2, end_cut2 = sec_filings._trim_to_sentence(
    frag, frag.index("Widget Corp"), len("Widget Corp"),
)
assert start_cut2, "문장 시작을 못 찾았는데 잘림 표시가 안 됨"
assert not end_cut2, "문장 끝은 온전한데 잘림으로 표시됨"
print("6b) 시작 경계를 못 찾으면 잘림(start_cut) 표시 OK")

# 6c) 문장의 앞뒤 경계는 둘 다 온전히 잡혔는데(=window 안에 다 들어옴) 문장 자체가 표시
# 상한(_MAX_SENTENCE_CHARS)을 넘는 경우 — 법률 문서 특유의 장문 나열. window를 넉넉히 줘서
# 경계 탐색 자체는 문제 없게 하고, 상한 절단만 단독으로 검증한다.
long_sentence = (
    "In 2028 the Company will " + ("supply many widgets and various components " * 10)
    + "to Widget Corp under the terms described herein."
)
assert len(long_sentence) > sec_filings._MAX_SENTENCE_CHARS, "테스트 문장이 상한보다 짧음"
LONG_DOC = "<p>Filler. " + long_sentence + " More filler after.</p>"

def fake_get_long(url, **kwargs):
    assert kwargs.get("stream") is True
    resp = FakeResponse(LONG_DOC)
    last_response["r"] = resp
    return resp

sec_filings.requests.get = fake_get_long
sentence3 = sec_filings._stream_find_context(
    "http://fake/long.htm", ["Widget Corp"], window=len(LONG_DOC),
)
sec_filings.requests.get = fake_get  # 이후 테스트를 위해 원래 fake로 복원
assert sentence3, "긴 문장에서 스니펫을 못 뽑음"
assert not sentence3.startswith("…"), f"경계를 다 잡았는데 시작이 잘림으로 표시됨: {sentence3!r}"
assert sentence3.endswith("…"), f"상한을 넘었는데 말줄임이 안 붙음: {sentence3!r}"
assert not sentence3[:-1].endswith(" "), f"단어 중간이 아니라 공백 경계에서 잘려야 함: {sentence3[-20:]!r}"
assert len(sentence3) <= sec_filings._MAX_SENTENCE_CHARS + 1, f"상한보다 길게 남음: {len(sentence3)}자"
print(f"6c) 긴 문장 상한 절단 OK ({len(sentence3)}자): 끝부분 {sentence3[-40:]!r}")

print("\n문장 경계 다듬기 전부 통과")

# --- 7) 여러 매칭 후보 중 실제 거래 내용을 고르는지 (2026-07-27 추가) -----------------
# 실측(RDW 검색)에서 첫 매칭이 전부 "we compete against ... including Airbus" 같은
# Risk Factors 경쟁사 나열이었던 문제를 재현 — 경쟁사 나열(먼저 나옴, 노이즈 키워드
# 포함) vs 실제 계약 설명(나중에 나옴, 금액·연도·계약 키워드 포함) 두 문장을 같은
# 문서에 넣고, 점수가 높은(=실제 계약을 설명하는) 쪽을 고르는지 확인한다.
NOISE_SENTENCE = "We compete against several providers, including Widget Corp, in various end markets."
DEAL_SENTENCE = (
    "In 2028, the Company entered into a $30 million supply agreement with Widget Corp "
    "for advanced components."
)
MULTI_DOC = (
    "<p>Item 1A. Risk Factors. " + ("Boilerplate risk language. " * 50)
    + NOISE_SENTENCE + " " + ("More boilerplate risk language. " * 300)
    + "</p><p>Item 1. Business. " + DEAL_SENTENCE
    + (" Filler business language." * 300) + "</p>"
)
assert NOISE_SENTENCE in MULTI_DOC and DEAL_SENTENCE in MULTI_DOC

def fake_get_multi(url, **kwargs):
    assert kwargs.get("stream") is True
    resp = FakeResponse(MULTI_DOC)
    last_response["r"] = resp
    return resp

sec_filings.requests.get = fake_get_multi
sec_filings._SNIPPET_CACHE.clear()
picked = sec_filings._extract_context_snippet("http://fake/multi.htm", "Widget Corp")
sec_filings.requests.get = fake_get  # 이후 테스트를 위해 원래 fake로 복원
assert picked, "매칭 후보에서 스니펫을 못 뽑음"
assert "$30 million" in picked and "supply agreement" in picked, \
    f"경쟁사 나열이 아니라 실제 계약 문장을 골라야 하는데 못 골랐음: {picked!r}"
assert "compete against" not in picked, f"경쟁사 나열 문장이 선택됨: {picked!r}"
print(f"7) 여러 후보 중 실제 계약 문장 선택 OK: {picked!r}")

# 7b) _score_sentence 자체도 단독으로 — 노이즈 문장보다 계약 문장 점수가 더 높은지,
# Risk Factors 섹션 근처라는 사실만으로도 감점되는지
noise_pos = MULTI_DOC.index(NOISE_SENTENCE)
deal_pos = MULTI_DOC.index(DEAL_SENTENCE)
noise_score = sec_filings._score_sentence(NOISE_SENTENCE, MULTI_DOC, noise_pos)
deal_score = sec_filings._score_sentence(DEAL_SENTENCE, MULTI_DOC, deal_pos)
assert deal_score > noise_score, f"계약 문장 점수가 더 높아야 함: 계약={deal_score}, 경쟁사={noise_score}"
assert sec_filings._section_penalty(MULTI_DOC, noise_pos) < 0, "Risk Factors 섹션 감점이 안 걸림"
assert sec_filings._section_penalty(MULTI_DOC, deal_pos) == 0, "Business 섹션인데 감점됨"
print(f"7b) 스코어링 세부 확인 OK: 계약 문장 {deal_score}점 > 경쟁사 나열 {noise_score}점 "
      f"(Risk Factors 섹션 감점 반영)")

print("\n후보 스코어링 전부 통과")
