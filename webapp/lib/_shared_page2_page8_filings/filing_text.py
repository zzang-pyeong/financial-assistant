"""SEC 공시/공시첨부문서를 스트리밍으로 받아 정리하고, 특정 문구 주변을 문장 단위로
잘라내는 범용 유틸리티. lib/sec_filings.py(관계도)와 lib/financials.py(재무제표 경영진
코멘트)가 공통으로 쓰는 부분만 여기 있음 — "어떤 문장이 그럴듯한가" 점수화 로직은
용도마다 달라서(관계 설명 vs 재무 항목 설명) 각 호출부가 score_sentence 콜백으로 넘긴다.

2026-07-28: lib/sec_filings.py에서 추출. 동작은 그대로, 위치만 옮김.
"""

import codecs
import html
import re

import requests

_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_ANY_TAG_RE = re.compile(r"<[^>]+>")

# 최신 10-K/10-Q는 Inline XBRL이라, 문서 맨 앞(<body> 직후)에 눈에 안 보이는
# <ix:header>가 있고 그 안에 전체 XBRL context/unit 정의가 들어있다. 이 정의들은
# "mp:AppleMember"처럼 태그의 텍스트 내용 자체가 회사명을 포함해서, 일반 태그 제거만으론
# 안 걸러지고 문구 매칭에 그대로 잡힌다(실측: MP Materials 10-Q에서 "Apple" 검색 시 실제
# 서술 문장("entered into a long-term supply agreement with Apple...")보다 이 헤더 안의
# "mp:AppleMember" 반복이 훨씬 먼저 나와서, max_candidates를 헤더 안에서 전부 소진해버려
# 진짜 문장에는 도달하지도 못했다). <ix:header>는 보통 수십~수백KB로 스트리밍 청크
# 하나보다 커서 여러 청크에 걸쳐 나뉘므로, 청크 간 상태(in_header)를 이어받아 처리한다.
_IX_HEADER_OPEN_RE = re.compile(r"<ix:header\b", re.IGNORECASE)
_IX_HEADER_CLOSE_RE = re.compile(r"</ix:header\s*>", re.IGNORECASE)


def strip_hidden_ixbrl_header(raw, in_header):
    """raw(태그가 청크 경계에서 잘리지 않도록 이미 안전하게 자른 조각)에서 <ix:header>
    블록을 제거한다. (남길 raw, 갱신된 in_header) 튜플을 반환 — in_header를 다음 호출에
    그대로 넘기면 여러 청크에 걸친 헤더도 올바르게 처리된다."""
    out = []
    pos = 0
    while True:
        if in_header:
            m = _IX_HEADER_CLOSE_RE.search(raw, pos)
            if not m:
                return "", True
            pos = m.end()
            in_header = False
        else:
            m = _IX_HEADER_OPEN_RE.search(raw, pos)
            if not m:
                out.append(raw[pos:])
                return "".join(out), False
            out.append(raw[pos:m.start()])
            pos = m.start()
            in_header = True

# 스트리밍 중 이 크기를 넘게 읽었는데도 매칭을 한 번도 못 찾으면 포기한다(비정상적으로
# 큰 첨부가 붙은 공시로부터 스스로를 보호). 실측상 매칭은 보통 앞쪽 수백 KB 안에 나온다.
_MAX_FILING_BYTES = 6 * 1024 * 1024
_STREAM_CHUNK = 64 * 1024

# 여러 매칭 후보를 모으기 위한 상한 — 첫 매칭에서 바로 멈추는 것보다는 더 읽어야 한다.
# 그래도 6MB 안전장치보다는 훨씬 작게 잡아서 대부분의 문서는 이 안에서 여러 매칭을
# 확보하고 끝난다. 이 안에서 하나도 못 찾은 극히 일부 문서만 _MAX_FILING_BYTES까지
# 계속 읽어 최소 1건은 건지려 한다(재현율 유지).
_CANDIDATE_SCAN_BYTES = 1_500_000
_MAX_CANDIDATES = 6


def clean_fragment(fragment):
    """HTML 조각에서 태그를 벗기고 엔티티를 풀어 공백을 정규화한다."""
    text = _SCRIPT_STYLE_RE.sub(" ", fragment)
    text = _ANY_TAG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", html.unescape(text))


def safe_split_point(raw):
    """조각 끝에 태그가 잘려 걸쳐 있으면(예: "...<td cla") 그 앞까지만 이번에 처리하고
    나머지는 다음 조각과 이어 붙이도록, 안전하게 자를 수 있는 위치를 돌려준다."""
    last_open = raw.rfind("<")
    if last_open == -1:
        return len(raw)
    return len(raw) if raw.find(">", last_open) != -1 else last_open


# 마침표 뒤에 대문자/인용부호가 오는 지점만 문장 끝으로 인정해 "Inc."·"U.S." 같은
# 약어의 마침표를 오판할 여지를 조금 줄인다 — 완벽하진 않다.
_SENTENCE_BOUNDARY_RE = re.compile(r'(?<=[.!?])\s+(?=[A-Z"‘“])')
_MAX_SENTENCE_CHARS = 320


def trim_to_sentence(text, match_start, match_len):
    """text 안에서 [match_start, match_start+match_len) 구간을 포함하는 문장만 골라
    반환한다. (문장, 시작이_잘렸는지, 끝이_잘렸는지) 튜플."""
    bounds = [0] + [m.end() for m in _SENTENCE_BOUNDARY_RE.finditer(text)] + [len(text)]
    match_end = match_start + match_len
    for i in range(len(bounds) - 1):
        s, e = bounds[i], bounds[i + 1]
        if s <= match_start < e:
            while e < match_end and i + 1 < len(bounds) - 1:
                i += 1
                e = bounds[i + 1]
            return text[s:e].strip(), s == 0, e == len(text)
    return text.strip(), True, True


def find_all_occurrences(tail, phrases, max_candidates):
    """tail 안에서 phrases 중 하나라도 매칭되는 지점을 등장 순서대로 최대
    max_candidates개 찾아 [(위치, 매칭길이), ...]로 반환."""
    lowered = [(p, p.lower()) for p in phrases]
    low = tail.lower()
    found = []
    search_from = 0
    while len(found) < max_candidates:
        best = None
        for phrase, phrase_low in lowered:
            idx = low.find(phrase_low, search_from)
            if idx != -1 and (best is None or idx < best[0]):
                best = (idx, len(phrase))
        if best is None:
            break
        found.append(best)
        search_from = best[0] + best[1]
    return found


def stream_find_context(
    url, phrases, score_sentence, user_agent, window=260,
    max_candidates=_MAX_CANDIDATES, candidate_scan_bytes=_CANDIDATE_SCAN_BYTES,
    max_filing_bytes=_MAX_FILING_BYTES, stream_chunk=_STREAM_CHUNK,
):
    """문서를 스트리밍으로 받으며 phrases가 나오는 지점을 최대 max_candidates개까지 모아
    (최대 candidate_scan_bytes, 하나도 못 찾았으면 max_filing_bytes까지 계속),
    score_sentence(sentence, tail, pos) 콜백으로 가장 그럴듯한 문장을 골라 반환한다.
    못 찾으면 None."""
    if not phrases:
        return None

    tail = ""
    carry = ""
    total = 0
    occurrences = []
    in_header = False

    try:
        with requests.get(
            url, headers={"User-Agent": user_agent}, timeout=15, stream=True,
        ) as r:
            # SEC EDGAR는 Content-Type에 charset을 안 붙여 보내서 requests가 r.encoding을
            # ISO-8859-1로 잘못 추측한다(HTTP 스펙상 text/* 기본값) — 실제 문서는 항상
            # UTF-8이라, 그 추측을 따르면 커브드 따옴표 같은 멀티바이트 문자가 깨진다
            # (실측: "Company's"가 "Company\x99s" 식으로 깨짐). 항상 UTF-8로 디코딩한다.
            decoder = codecs.getincrementaldecoder("utf-8")(errors="ignore")
            for chunk in r.iter_content(chunk_size=stream_chunk):
                if not chunk:
                    continue
                total += len(chunk)
                raw = carry + decoder.decode(chunk)
                cut = safe_split_point(raw)
                carry = raw[cut:]
                visible, in_header = strip_hidden_ixbrl_header(raw[:cut], in_header)
                tail += clean_fragment(visible)

                occurrences = find_all_occurrences(tail, phrases, max_candidates)
                if len(occurrences) >= max_candidates:
                    break
                if occurrences and len(tail) >= candidate_scan_bytes:
                    break
                if total > max_filing_bytes:
                    break
    except Exception:
        return None

    if not occurrences:
        return None

    candidates = []
    for found_at, found_len in occurrences:
        start = max(0, found_at - window)
        end = min(len(tail), found_at + found_len + window)
        raw = tail[start:end]
        sentence, start_cut, end_cut = trim_to_sentence(raw, found_at - start, found_len)
        if len(sentence) > _MAX_SENTENCE_CHARS:
            sentence = sentence[:_MAX_SENTENCE_CHARS].rsplit(" ", 1)[0].rstrip(",;:")
            end_cut = True
        candidates.append((sentence, start_cut, end_cut, found_at))

    sentence, start_cut, end_cut, _pos = max(
        candidates, key=lambda c: score_sentence(c[0], tail, c[3]),
    )
    prefix = "…" if start_cut else ""
    suffix = "…" if end_cut else ""
    return prefix + sentence + suffix
