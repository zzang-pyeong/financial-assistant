"""뉴스 헤드라인 한글 번역 + 한글 검색어 영문 변환.

⚠️ 왜 deep_translator의 `translate_batch()`를 안 쓰는가 (2026-07-27 소스 확인):
`GoogleTranslator.translate_batch()`는 이름과 달리 여러 문장을 한 요청으로 묶어 보내지
않는다 — `BaseTranslator._translate_batch()`가 그냥 파이썬 for문으로 `translate()`를
하나씩 호출한다(deep_translator 1.11.4 `base.py:171-183` 확인). 즉 HTTP 요청 수가 전혀
줄지 않아 배치로 바꿔봐야 아무 이득이 없다. 그래서 요청 수를 줄이는 대신 **동시에**
보내는 방향(prefetch_korean)을 택했다.

구분자로 여러 헤드라인을 한 문자열에 이어붙여 1회 요청으로 만드는 방법도 검토했으나,
번역기가 구분자를 그대로 보존한다는 보장이 없어 잘못 쪼개질 위험이 있어서 제외했다
(요청 수 절감보다 결과 정합성이 중요한 자리).
"""

from concurrent.futures import ThreadPoolExecutor

import streamlit as st
from deep_translator import GoogleTranslator

# 번역 결과 캐시 — 같은 영문 헤드라인은 언제 번역해도 결과가 같으므로 프로세스 단위로 공유한다
# (st.cache_data도 어차피 프로세스 범위라 공유 범위는 동일하다). st.cache_data 대신 평범한
# dict을 쓰는 이유는 prefetch_korean()이 워커 스레드에서 번역을 돌리기 때문 — 스레드에서
# st.cache_data 함수를 호출하면 ScriptRunContext 경고가 뜨고, 무엇보다 배치로 미리 채운
# 결과가 개별 to_korean() 호출의 캐시 키와 안 맞아 캐시 미스가 나버린다.
_KO_CACHE = {}
_KO_CACHE_MAX = 5000

# 동시 요청 수 — 구글 번역 비공식 엔드포인트는 과하게 때리면 429(TooManyRequests)를 준다.
# 헤드라인 30건 기준 6이면 순차 대비 체감이 확 달라지면서도 429를 부르지 않는 선이다.
_TRANSLATE_WORKERS = 6


def _remember(text, result):
    """캐시가 무한정 커지지 않도록 상한을 두고, 넘치면 오래된 쪽부터 20%를 버린다
    (dict은 삽입 순서를 보존하므로 앞쪽이 오래된 항목이다)."""
    if len(_KO_CACHE) >= _KO_CACHE_MAX:
        for k in list(_KO_CACHE)[: _KO_CACHE_MAX // 5]:
            _KO_CACHE.pop(k, None)
    _KO_CACHE[text] = result


def _translate_one(text):
    """실제 번역 1건. 캐시도 Streamlit 의존성도 없어 워커 스레드에서 호출해도 안전하다.
    실패 시 원문 그대로 반환 — 다른 lib 함수들과 같은 '조용한 폴백' 패턴."""
    try:
        return GoogleTranslator(source="en", target="ko").translate(text)
    except Exception:
        return text


def to_korean(text):
    """영문 뉴스 헤드라인을 한글로 번역. 실패 시 원문 그대로 반환.
    prefetch_korean()이 미리 채워둔 게 있으면 네트워크 호출 없이 즉시 반환한다."""
    if not text:
        return text
    cached = _KO_CACHE.get(text)
    if cached is not None:
        return cached
    result = _translate_one(text)
    _remember(text, result)
    return result


def prefetch_korean(texts):
    """화면에 곧 뿌릴 헤드라인들을 미리 병렬 번역해 캐시에 채운다.

    이걸 안 쓰면 to_korean()이 렌더 도중에 헤드라인 수(최대 30건)만큼 순차 HTTP 요청을
    보내게 되는데, 그 시점은 데이터 수집 스피너가 이미 끝난 뒤라 사용자에게는 아무 안내
    없이 화면이 굳은 것처럼 보인다. 수집 단계(스피너 안)에서 이 함수를 먼저 부르면
    (1) 대기 시간이 스피너 안으로 들어가 이유가 보이고 (2) 동시 요청으로 실제 시간도 줄어든다.

    이미 캐시에 있는 항목과 중복은 건너뛴다. 실패한 항목은 _translate_one()이 원문을
    돌려주므로 화면은 영문 헤드라인으로 자연스럽게 폴백된다."""
    pending = [t for t in dict.fromkeys(texts) if t and t not in _KO_CACHE]
    if not pending:
        return
    with ThreadPoolExecutor(max_workers=min(_TRANSLATE_WORKERS, len(pending))) as executor:
        # executor.map은 입력 순서대로 결과를 돌려주므로 zip으로 짝지어도 안전하다
        for text, result in zip(pending, executor.map(_translate_one, pending)):
            _remember(text, result)


@st.cache_data(ttl=86400, show_spinner=False)
def to_english(text):
    """한글 등으로 입력된 기업명을 영문으로 번역 (티커 검색용). 실패 시 원문 그대로 반환.
    검색 1회당 1건뿐이라 병렬화 대상이 아니라서 기존 st.cache_data를 그대로 둔다."""
    if not text:
        return text
    try:
        return GoogleTranslator(source="auto", target="en").translate(text)
    except Exception:
        return text
