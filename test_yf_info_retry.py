"""get_yf_info() 재시도 로직 검증 (2026-07-30). Streamlit 없이 lib.data만 직접 불러
yfinance의 .info가 간헐적으로 빈 dict를 돌려줄 때(실측: 배포판에서 시가총액·직원 수 등
회사 프로필 필드가 전부 N/A로 뜨는 문제 — 로컬에서 배포판과 동일한 yfinance 버전으로
직접 재현했을 때는 정상 동작해 Yahoo Finance의 클라우드 호스팅 IP 차단/제한으로 추정)
재시도로 복구되는지, 계속 실패하면 정직하게 빈 dict로 폴백하는지 확인한다."""
import sys
sys.path.insert(0, "webapp")

from unittest.mock import patch
import lib._shared_core.data as data

# 1) 간헐적 실패(처음 두 번은 빈 dict, 세 번째에 성공) — 재시도로 복구돼야 한다.
call_count = {"n": 0}


class _TransientlyFailingTicker:
    def __init__(self, ticker):
        pass

    @property
    def info(self):
        call_count["n"] += 1
        if call_count["n"] < 3:
            return {}
        return {"marketCap": 12345, "shortName": "Test Co"}


with patch.object(data.yf, "Ticker", _TransientlyFailingTicker), \
     patch.object(data.time, "sleep", lambda *_: None):
    data.get_yf_info.clear()
    result = data.get_yf_info("TESTX")
    assert call_count["n"] == 3, f"재시도 횟수가 다름: {call_count['n']}"
    assert result.get("marketCap") == 12345, f"일시적 실패에서 복구 못함: {result}"
    print("1) 간헐적 실패(2회) 후 재시도로 복구 OK")

# 2) 계속 실패(항상 빈 dict) — 무한 재시도하지 않고 정확히 3번만 시도한 뒤 빈 dict로
#    폴백해야 한다.
call_count["n"] = 0


class _AlwaysEmptyTicker:
    def __init__(self, ticker):
        pass

    @property
    def info(self):
        call_count["n"] += 1
        return {}


with patch.object(data.yf, "Ticker", _AlwaysEmptyTicker), \
     patch.object(data.time, "sleep", lambda *_: None):
    data.get_yf_info.clear()
    result = data.get_yf_info("TESTY")
    assert call_count["n"] == 3, f"계속 실패인데도 재시도 횟수가 다름: {call_count['n']}"
    assert result == {}, f"지속 실패 시 빈 dict로 폴백 안 됨: {result}"
    print("2) 지속적 실패 시 3회만 시도하고 빈 dict로 정직하게 폴백 OK")

# 3) 첫 시도에 바로 성공하면 불필요한 재시도 없이 즉시 반환해야 한다(정상 케이스 지연 방지).
call_count["n"] = 0


class _ImmediateSuccessTicker:
    def __init__(self, ticker):
        pass

    @property
    def info(self):
        call_count["n"] += 1
        return {"marketCap": 999, "shortName": "Fast Co"}


with patch.object(data.yf, "Ticker", _ImmediateSuccessTicker), \
     patch.object(data.time, "sleep", lambda *_: None):
    data.get_yf_info.clear()
    result = data.get_yf_info("TESTZ")
    assert call_count["n"] == 1, f"첫 시도 성공인데도 불필요하게 재시도함: {call_count['n']}"
    assert result.get("marketCap") == 999
    print("3) 첫 시도 성공 시 불필요한 재시도 없이 즉시 반환 OK (정상 케이스 지연 방지)")

print("\nyfinance 재시도 로직 전부 통과")
