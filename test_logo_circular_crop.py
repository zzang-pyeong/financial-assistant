"""로고 원형 크롭 검증 (2026-07-27). 네트워크 없이 PIL로 가짜 로고를 만들어
(1) 원형 알파 마스크가 실제로 씌워지는지 (2) 모서리가 투명해지는지
(3) 워드마크형(가로로 긴 로고)은 잘리지 않는지 (4) SVG는 폴백되는지를 확인한다."""
import base64
import sys
from io import BytesIO

sys.path.insert(0, "webapp")
from PIL import Image, ImageDraw

# lib._shared_core.data는 FinanceDataReader를 import하는데, 이 검증 환경에서는 그 패키지의
# pyOpenSSL 의존성이 깨져 있다(우리 코드와 무관한 환경 문제). 로고 크롭 검증에 Finnhub 조회는
# 필요 없으므로 lib._shared_core.data를 스텁으로 갈아끼워 lib.page8_only_relationship.logos만
# 떼어내 테스트한다.
import types
_stub = types.ModuleType("lib._shared_core.data")
_stub.get_company_logo_url = lambda ticker: None
sys.modules["lib._shared_core.data"] = _stub

from lib.page8_only_relationship import logos as L


def make_png(w, h, color=(200, 30, 30, 255), transparent_bg=False):
    """가운데에 색 사각형이 있는 테스트 이미지."""
    bg = (0, 0, 0, 0) if transparent_bg else (255, 255, 255, 255)
    im = Image.new("RGBA", (w, h), bg)
    d = ImageDraw.Draw(im)
    d.rectangle((w * 0.2, h * 0.2, w * 0.8, h * 0.8), fill=color)
    buf = BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def decode(uri):
    assert uri.startswith("data:image/png;base64,"), f"data URI 형식이 아님: {uri[:40]}"
    return Image.open(BytesIO(base64.b64decode(uri.split(",", 1)[1]))).convert("RGBA")


# --- 1) 정사각 로고 → 원형으로 잘림 ---------------------------------------------------
uri, cropped = L._circular_png_data_uri(make_png(256, 256))
assert uri and cropped, f"정사각 로고인데 크롭 안 됨 (cropped={cropped})"
im = decode(uri)
w, h = im.size
assert w == h == L._LOGO_PX, f"출력 크기 이상: {im.size}"

corners = [im.getpixel(p)[3] for p in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]]
center_alpha = im.getpixel((w // 2, h // 2))[3]
edge_mid = [im.getpixel(p)[3] for p in [(w // 2, 1), (1, h // 2)]]
assert all(a == 0 for a in corners), f"모서리가 안 잘림 (alpha={corners})"
assert center_alpha == 255, f"가운데가 투명함 (alpha={center_alpha})"
assert all(a > 200 for a in edge_mid), f"원의 상/좌 중앙이 잘림 (alpha={edge_mid})"
print(f"1) 정사각 로고 원형 크롭 OK — 모서리 alpha={corners}, 가운데 {center_alpha}, "
      f"원 둘레 중앙 {edge_mid}")

# 실제로 원 모양인지: 알파>0 픽셀 비율이 원 면적비(pi/4 ~ 0.785)에 가까운지
opaque = sum(1 for y in range(h) for x in range(w) if im.getpixel((x, y))[3] > 127)
ratio = opaque / (w * h)
assert 0.75 < ratio < 0.82, f"원 면적비가 이상함: {ratio:.3f} (기대 ~0.785)"
print(f"2) 채워진 면적비 {ratio:.3f} — 원(pi/4=0.785)과 일치 OK")

# --- 3) 투명 배경 로고 → 흰 바탕이 깔리는지 -------------------------------------------
uri_t, _ = L._circular_png_data_uri(make_png(256, 256, transparent_bg=True))
im_t = decode(uri_t)
# 로고 그림이 없는 안쪽 여백(원 안, 사각형 밖) 지점이 흰색이어야 함
px = im_t.getpixel((L._LOGO_PX // 2, 6))
assert px[3] > 200 and px[0] > 240 and px[1] > 240, f"투명 배경이 흰색으로 안 깔림: {px}"
print(f"3) 투명 배경 → 흰 바탕 깔림 OK (원 안 여백 픽셀 {px})")

# --- 4) 가로로 긴 워드마크형 → 자르지 않음 --------------------------------------------
uri_w, cropped_w = L._circular_png_data_uri(make_png(400, 100))
assert uri_w, "워드마크 로고 변환 실패"
assert not cropped_w, "워드마크형인데 가운데를 잘라버림 (글자가 날아간다)"
print(f"4) 워드마크형(400x100, 비율 4.0) 크롭 안 함 OK — 임계값 {L._MAX_CROP_ASPECT}")

uri_s, cropped_s = L._circular_png_data_uri(make_png(300, 220))   # 비율 1.36 < 1.6
assert cropped_s, "거의 정사각(1.36)인데 크롭을 건너뜀"
print(f"5) 거의 정사각(300x220, 비율 1.36) 크롭 함 OK")

# --- 6) SVG / 깨진 데이터 → None 폴백 -------------------------------------------------
svg = b'<svg xmlns="http://www.w3.org/2000/svg"><circle r="5"/></svg>'
assert L._circular_png_data_uri(svg) == (None, False), "SVG인데 None 폴백 안 함"
assert L._circular_png_data_uri(b"not-an-image") == (None, False), "깨진 데이터 폴백 안 함"
print("6) SVG·손상 데이터 → None 폴백 OK (호출부가 원본 URL로 내접 처리)")

# --- 7) data URI 크기 (rerun마다 브라우저로 전송되므로) --------------------------------
kb = len(uri) / 1024
assert kb < 60, f"data URI가 너무 큼: {kb:.1f}KB"
print(f"7) data URI 크기 {kb:.1f}KB — 노드 10개면 약 {kb*10:.0f}KB")

# --- 8) 그래프에 꽂았을 때 원을 채우는지 -----------------------------------------------
from lib._shared_core.charts import (
    render_relationship_graph_figure, _NODE_RADIUS, _LOGO_FIT_CIRCULAR, _LOGO_FIT_SQUARE,
)

edges = [{
    "counterparty_ticker": "AAA", "counterparty_name": "Alpha Inc.",
    "relationship_type": "공급 계약", "status": "체결·진행", "evidence_level": "테스트",
    "headline": "h", "url": "https://x", "datetime": 1_700_000_000, "context": None,
}]
fig_c = render_relationship_graph_figure("HUB", "Hub Corp", edges,
                                         logos={"AAA": {"src": uri, "circular": True}})
img_c = fig_c.layout.images[0]
assert abs(img_c.sizex - _NODE_RADIUS * _LOGO_FIT_CIRCULAR) < 1e-9
fill_ratio = img_c.sizex / (2 * _NODE_RADIUS)
assert fill_ratio > 0.9, f"원을 못 채움: {fill_ratio:.2f}"
print(f"8) 원형 로고는 원 지름의 {fill_ratio*100:.0f}%를 채움 OK "
      f"(테두리 링이 안 덮이게 일부러 100% 미만)")

fig_s = render_relationship_graph_figure("HUB", "Hub Corp", edges,
                                         logos={"AAA": {"src": "https://x.svg", "circular": False}})
img_s = fig_s.layout.images[0]
import math
assert (img_s.sizex / 2) * math.sqrt(2) <= _NODE_RADIUS * 1.001, "네모난 로고가 원 밖으로 나감"
print(f"9) 네모난(폴백) 로고는 원에 내접 OK — 원 지름의 "
      f"{img_s.sizex/(2*_NODE_RADIUS)*100:.0f}%")

# 문자열로 넘겨도(구버전 호출 방식) 죽지 않는지
fig_str = render_relationship_graph_figure("HUB", "Hub", edges, logos={"AAA": "https://x.png"})
assert len(fig_str.layout.images) == 1
print("10) logos에 URL 문자열을 넘기는 옛 방식도 호환 OK (네모난 이미지로 취급)")

print("\n전부 통과")
