"""SEC 공시 스니펫 추출의 스트리밍 조기 종료 검증 (2026-07-27).

실제 SEC를 호출하지 않고 requests.get을 가짜로 갈아끼워, 6MB짜리 가짜 10-K에서
(1) 회사명을 찾는 즉시 연결을 끊는지 — 실제로 몇 바이트만 읽고 멈추는지
(2) 청크 경계에 태그/회사명이 걸쳐도 스니펫이 깨지지 않는지
(3) 언급이 없으면 문서를 다 훑고도 None을 돌려주는지
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

# --- 1) 조기 종료 -----------------------------------------------------------------
sec_filings._SNIPPET_CACHE.clear()
snippet = sec_filings._extract_context_snippet(
    "http://fake/10k.htm", "Taiwan Semiconductor Manufacturing Company Limited",
)
read_mb = last_response["r"].bytes_read / 1024 / 1024
total_mb = len(FAKE_10K.encode()) / 1024 / 1024
assert snippet, "스니펫을 못 뽑음"
print(f"\n1) 조기 종료: 전체 {total_mb:.1f}MB 중 {read_mb:.2f}MB만 읽고 중단 "
      f"({read_mb/total_mb*100:.1f}%)")
assert read_mb < total_mb * 0.1, f"조기 종료 실패 — {read_mb:.2f}MB나 읽음"

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

# --- 5) 이전 구현 대비 다운로드량 -----------------------------------------------------
# ⚠️ 아래 배율은 이 가짜 문서 기준이다. 실제 NVDA 10-K 본문(nvda-20260125.htm)은 약 1.9MB이고
# (SEC 공시 인덱스에서 확인), 11MB로 표시되는 건 XBRL까지 포함한 complete submission 파일이다.
# 우리가 받는 URL은 본문 쪽이므로 실제 절감폭은 "20건 x 1.9MB ≈ 38MB → 10건 x 조기종료분"이다.
ratio = read_mb / total_mb
print(f"\n5) 조기 종료 비율 {ratio*100:.1f}% — 실제 10-K 본문 1.9MB 기준으로 환산하면 "
      f"상위 20건 {1.9*20:.0f}MB → 상위 10건 {1.9*ratio*10:.1f}MB 수준")

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
