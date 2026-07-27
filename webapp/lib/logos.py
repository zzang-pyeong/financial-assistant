"""회사 로고를 관계도 노드(원)에 꽉 채워 넣기 위한 원형 크롭 (2026-07-27).

왜 서버에서 이미지를 가공하는가: plotly의 layout image는 사각형으로만 배치되고 원형
클리핑을 지원하지 않는다. 그래서 로고를 원 안에 "내접"시키면 원의 가장자리가 늘 비어
보인다. 원을 꽉 채우려면 **이미지 자체가 원형**이어야 해서, 받아온 로고를 가운데
정사각형으로 자르고 원형 알파 마스크를 씌운 PNG로 다시 만들어 data URI로 넘긴다.

plotly의 shape path로 사각형-빼기-원 마스크를 덮는 방법도 검토했지만 두 가지 이유로
버렸다: (1) plotly shape path는 SVG 원호(A) 명령을 지원하지 않아 원을 베지어로 근사해야
한다 (2) 무엇보다 shape과 image의 그리기 순서(어느 쪽이 위로 오는지)에 의존하는데,
그건 plotly 내부 레이어 순서라 우리가 보장할 수 없다. 지금 방식은 이미지 하나로 끝나서
렌더링 순서에 의존하지 않는다.

Pillow은 streamlit의 필수 의존성이므로 새로 추가되는 의존성이 아니다(streamlit이
pillow를 requires에 갖고 있음 — 확인함). 그래도 명시적으로 requirements.txt에 적어둔다.
"""

import base64
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

import requests

from .data import get_company_logo_url

# 노드는 화면에서 약 40px이라 96px이면 고해상도 화면에서도 충분하다. 더 키우면 base64
# 문자열이 커지는데, 이 data URI는 Streamlit이 rerun마다 그림 JSON에 담아 브라우저로
# 보내므로(노드 10개면 매번 100KB대) 필요 이상으로 키우지 않는다.
_LOGO_PX = 96

# 가로세로 비율이 이보다 더 찌그러진 로고는 가운데를 자르지 않는다. 정사각 아이콘형은
# 잘라도 멀쩡하지만, 가로로 긴 워드마크형(회사 이름을 글자로 쓴 로고)을 원으로 자르면
# 글자 두어 개만 남아 오히려 못 알아본다 — 그런 경우는 원 안에 작게 내접시키는 게 낫다.
_MAX_CROP_ASPECT = 1.6

_CIRCULAR_CACHE = {}
_CIRCULAR_CACHE_MAX = 500
_TIMEOUT = 10


def _download(url):
    try:
        r = requests.get(url, timeout=_TIMEOUT)
        if r.status_code != 200 or not r.content:
            return None
        return r.content
    except Exception:
        return None


def _circular_png_data_uri(image_bytes):
    """받아온 이미지를 원형 PNG data URI로 변환. 변환 불가(SVG 등 PIL이 못 읽는 형식,
    손상된 파일)면 None — 호출부는 이때 기존 방식(원 안에 내접)으로 폴백해야 한다.

    반환값 두 번째 원소는 잘라냈는지 여부(cropped) — 워드마크형처럼 자르면 안 되는
    로고는 자르지 않고 그대로 두므로, 호출부가 원을 꽉 채울지 내접시킬지 구분해야 한다."""
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return None, False

    try:
        im = Image.open(BytesIO(image_bytes))
        im.load()
    except Exception:
        return None, False   # SVG 등 PIL이 못 여는 형식

    try:
        im = im.convert("RGBA")
        # 투명 배경 로고를 그대로 원형으로 만들면 원 안이 비어 보인다 — 흰 바탕을 깔아
        # '흰 원 위의 로고'가 되게 한다(노드 원의 fill도 흰색이라 이어져 보인다).
        im = Image.alpha_composite(Image.new("RGBA", im.size, (255, 255, 255, 255)), im)

        w, h = im.size
        if not w or not h:
            return None, False
        aspect = max(w, h) / min(w, h)
        cropped = aspect <= _MAX_CROP_ASPECT
        if cropped:
            side = min(w, h)
            left, top = (w - side) // 2, (h - side) // 2
            im = im.crop((left, top, left + side, top + side))
        else:
            # 자르지 않는 대신 정사각 캔버스 가운데에 얹어 비율을 지킨다
            side = max(w, h)
            canvas = Image.new("RGBA", (side, side), (255, 255, 255, 255))
            canvas.paste(im, ((side - w) // 2, (side - h) // 2), im)
            im = canvas

        im = im.resize((_LOGO_PX, _LOGO_PX), Image.LANCZOS)

        # 원형 알파 마스크. 4배 크기로 그린 뒤 축소해 테두리를 부드럽게 한다(그냥 그리면
        # 원 둘레가 계단처럼 각져 보인다).
        scale = 4
        mask = Image.new("L", (_LOGO_PX * scale, _LOGO_PX * scale), 0)
        ImageDraw.Draw(mask).ellipse(
            (0, 0, _LOGO_PX * scale - 1, _LOGO_PX * scale - 1), fill=255,
        )
        im.putalpha(mask.resize((_LOGO_PX, _LOGO_PX), Image.LANCZOS))

        buf = BytesIO()
        im.save(buf, format="PNG", optimize=True)
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(), cropped
    except Exception:
        return None, False


def get_circular_logo(ticker):
    """{"src": data URI 또는 원본 URL, "circular": bool} 또는 None.

    - `circular=True`  → 이미지가 원형으로 가공됐다. 노드 원을 꽉 채워도 된다.
    - `circular=False` → 가공 실패(예: SVG 로고)해서 원본 URL을 그대로 넘긴다.
      네모난 이미지이므로 호출부는 원 안에 내접시켜야 모서리가 안 삐져나온다.
    - `None`           → 로고 자체가 없다(소형주에 흔함). 노드는 빈 원으로 그린다.

    캐시도 Streamlit 의존도 없어 워커 스레드에서 호출해도 안전하다
    (lib/translate.py·lib/sec_filings.py와 같은 이유·같은 패턴)."""
    if not ticker:
        return None
    key = ticker.upper()
    if key in _CIRCULAR_CACHE:
        return _CIRCULAR_CACHE[key]

    result = None
    url = get_company_logo_url(ticker)
    if url:
        data = _download(url)
        if data:
            uri, cropped = _circular_png_data_uri(data)
            if uri:
                result = {"src": uri, "circular": cropped}
            else:
                # 가공 실패 — 원본 URL로라도 보여준다(브라우저가 직접 받아 그림)
                result = {"src": url, "circular": False}

    if len(_CIRCULAR_CACHE) >= _CIRCULAR_CACHE_MAX:
        for k in list(_CIRCULAR_CACHE)[: _CIRCULAR_CACHE_MAX // 5]:
            _CIRCULAR_CACHE.pop(k, None)
    _CIRCULAR_CACHE[key] = result
    return result


def get_circular_logos(tickers, max_workers=6):
    """여러 티커의 로고를 병렬로 준비해 {티커: 로고정보} 로 반환(없는 건 아예 빼고 담는다).
    Finnhub 프로필 조회 1회 + 이미지 다운로드 1회가 티커당 붙으므로 순차로 하면 체감이
    나쁘다 — 관계도는 상위 10개 + 허브만 받으므로 워커 6개로 충분하다."""
    unique = [t for t in dict.fromkeys(tickers) if t]
    if not unique:
        return {}
    with ThreadPoolExecutor(max_workers=min(max_workers, len(unique))) as executor:
        results = list(executor.map(get_circular_logo, unique))
    return {t: r for t, r in zip(unique, results) if r}
