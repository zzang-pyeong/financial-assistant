"""관계도 노드를 섹터별로 묶기 위한 섹터 조회 (2026-07-27).

lib/data.py::get_yf_info()는 이미 있지만 @st.cache_data가 걸려있어 워커 스레드에서
호출하면 ScriptRunContext 경고가 난다(lib/translate.py·lib/logos.py·lib/sec_filings.py와
같은 이유). 상대기업이 많을 때(수십 개) 병렬로 빨리 받아야 해서, 여기서는 그 파일들과
같은 패턴(평범한 dict 캐시 + ThreadPoolExecutor)을 그대로 따른다."""

from concurrent.futures import ThreadPoolExecutor

import yfinance as yf

_SECTOR_CACHE = {}
_SECTOR_CACHE_MAX = 500


def _fetch_sector(ticker):
    try:
        return yf.Ticker(ticker).info.get("sector") or None
    except Exception:
        return None


def get_sector(ticker):
    """티커의 GICS 섹터명(예: "Technology") 또는 None(조회 실패·필드 없음)."""
    if not ticker:
        return None
    key = ticker.upper()
    if key in _SECTOR_CACHE:
        return _SECTOR_CACHE[key]
    result = _fetch_sector(ticker)
    if len(_SECTOR_CACHE) >= _SECTOR_CACHE_MAX:
        for k in list(_SECTOR_CACHE)[: _SECTOR_CACHE_MAX // 5]:
            _SECTOR_CACHE.pop(k, None)
    _SECTOR_CACHE[key] = result
    return result


def get_sectors(tickers, max_workers=6):
    """여러 티커의 섹터를 병렬로 조회해 {티커: 섹터명 또는 None} 으로 반환."""
    unique = [t for t in dict.fromkeys(tickers) if t]
    if not unique:
        return {}
    with ThreadPoolExecutor(max_workers=min(max_workers, len(unique))) as executor:
        results = list(executor.map(get_sector, unique))
    return dict(zip(unique, results))
