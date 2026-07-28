"""prefetch_korean/to_korean 캐시 동작 오프라인 검증 — 실제 번역 API는 호출하지 않고
_translate_one을 가짜로 갈아끼워 '몇 번 호출됐는지'만 센다."""
import sys, threading, time
sys.path.insert(0, "webapp")

from lib._shared_core import translate

_REAL_TRANSLATE_ONE = translate._translate_one   # 폴백 테스트에서 되돌리려고 원본 보관

calls = []
lock = threading.Lock()

def fake_translate_one(text):
    with lock:
        calls.append(text)
    time.sleep(0.05)          # 네트워크 왕복 흉내
    return "[KO]" + text

translate._translate_one = fake_translate_one

headlines = [f"Headline number {i}" for i in range(30)]
headlines.append("Headline number 0")   # 중복 — 한 번만 번역돼야 함

t0 = time.time()
translate.prefetch_korean(headlines)
elapsed = time.time() - t0

assert len(calls) == 30, f"중복 제거 실패: {len(calls)}회 호출됨"
print(f"1) 중복 제거: 31건 입력 → {len(calls)}회 번역 OK")
print(f"2) 병렬 처리: 30건 x 0.05초 = 순차라면 1.50초, 실제 {elapsed:.2f}초")
assert elapsed < 0.8, "병렬화가 동작하지 않음"

calls.clear()
out = [translate.to_korean(h) for h in headlines]
assert not calls, f"프리페치 후에도 재번역 발생: {calls}"
print(f"3) 렌더 단계 재요청 0회 OK (캐시 적중)")
assert out[0] == "[KO]Headline number 0"
print("4) 번역 결과 정상 반환 OK")

# 실패 폴백 — 번역기가 예외를 던져도 원문이 나와야 함
translate._KO_CACHE.clear()
translate._translate_one = _REAL_TRANSLATE_ONE
class FailingTranslator:
    def __init__(self, **kw): pass
    def translate(self, text): raise RuntimeError("차단됨")
translate.GoogleTranslator = FailingTranslator
assert translate.to_korean("Fallback test") == "Fallback test"
print("5) 번역 실패 시 원문 폴백 OK")

# 캐시 상한 — 넘치면 오래된 것부터 버리되 최신 항목은 남아야 함
translate._KO_CACHE.clear()
translate._KO_CACHE_MAX = 100
for i in range(150):
    translate._remember(f"k{i}", f"v{i}")
assert len(translate._KO_CACHE) <= 100, f"상한 초과: {len(translate._KO_CACHE)}"
assert "k149" in translate._KO_CACHE, "최신 항목이 사라짐"
print(f"6) 캐시 상한 OK (상한 100, 실제 {len(translate._KO_CACHE)}개, 최신 항목 보존)")
print("\n전부 통과")
