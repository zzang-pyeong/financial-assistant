"""관계도 그룹핑·배치·표 데이터 오프라인 검증 (2026-07-27).
Streamlit 없이 lib.charts만 직접 불러 (1) 그룹핑/정렬 (2) 노드 배치 겹침
(3) 근거 표에 들어갈 행이 제대로 만들어지는지를 확인한다."""
import math
import sys
sys.path.insert(0, "webapp")

from lib.charts import (
    group_relationship_edges, render_relationship_graph_figure,
    _node_positions, MAX_RELATIONSHIP_NODES,
)

def edge(cp, name, rtype, status, dt, url, context=None):
    return {
        "counterparty_ticker": cp, "counterparty_name": name,
        "relationship_type": rtype, "status": status, "evidence_level": "테스트",
        "headline": f"{cp} 관련 헤드라인", "url": url, "datetime": dt, "context": context,
    }

# 15개 회사 — 그래프 상한(10)을 넘겨서 잘림 처리를 확인
edges = []
for i in range(15):
    cp = f"CP{i:02d}"
    for j in range(i % 3 + 1):                     # 회사마다 근거 1~3건
        edges.append(edge(cp, f"Company {i} Inc.", "공시상 언급", "공시 확인",
                          1_700_000_000 + i * 1000 + j, f"https://sec.gov/{cp}/{j}",
                          context=f"...supply agreement with Company {i}..."))
edges.append(edge("CP00", "Company 0 Inc.", "인수합병(M&A)", "철회·무산",
                  1_750_000_000, "https://news/CP00"))
edges.append(edge("CP01", "Company 1 Inc.", "공급 계약", "체결·진행",
                  1_760_000_000, "https://news/CP01"))

grouped = group_relationship_edges(edges)

# 1) 그룹핑
assert len(grouped) == 15, f"회사 수 불일치: {len(grouped)}"
print(f"1) 그룹핑: 엣지 {len(edges)}건 → 상대기업 {len(grouped)}개 OK")

# 2) 정렬 — 근거 수 내림차순
counts = [len(g["headlines"]) for _, g in grouped]
assert counts == sorted(counts, reverse=True), f"정렬 깨짐: {counts}"
print(f"2) 정렬(근거 수 내림차순) OK: {counts}")

# 3) 소스별 카운트 분리
cp00 = dict(grouped)["CP00"]
assert cp00["news_count"] == 1 and cp00["filing_count"] == 1, \
    f"뉴스/공시 분리 실패: {cp00['news_count']}/{cp00['filing_count']}"
print(f"3) 소스별 분리 OK: CP00 = 뉴스 {cp00['news_count']}건 / 공시 {cp00['filing_count']}건")

# 4) 노드 배치 — 라벨이 겹칠 만큼 가까운 노드가 없는지
coords = _node_positions(MAX_RELATIONSHIP_NODES)
assert len(coords) == 10
first = coords[0]
assert abs(first[0]) < 1e-9 and first[1] > 0, f"12시 방향에서 시작하지 않음: {first}"
assert coords[1][0] > 0, "시계방향이 아님"
min_dist = min(
    math.dist(a, b) for i, a in enumerate(coords) for b in coords[i + 1:]
)
print(f"4) 배치 OK: 12시 시작·시계방향, 노드 간 최소거리 {min_dist:.3f}")
assert min_dist > 0.35, f"노드가 너무 붙음: {min_dist:.3f}"

flat = [math.dist(a, b) for i, a in enumerate([(math.cos(math.pi/2 - 2*math.pi*i/10), math.sin(math.pi/2 - 2*math.pi*i/10)) for i in range(10)])
        for b in [(math.cos(math.pi/2 - 2*math.pi*j/10), math.sin(math.pi/2 - 2*math.pi*j/10)) for j in range(10)] if a != b]
print(f"   (반지름 고정이었다면 최소거리 {min(flat):.3f} — 엇갈리게 배치해 {min_dist/min(flat):.2f}배 벌어짐)")

# 5) 그래프가 실제로 그려지는지 + 상한 적용
fig = render_relationship_graph_figure("NVDA", "NVIDIA Corporation", edges)
node_traces = [t for t in fig.data if t.mode == "markers+text" and t.text and len(t.text) > 1]
assert len(node_traces) == 1
assert len(node_traces[0].x) == MAX_RELATIONSHIP_NODES, \
    f"상한 미적용: {len(node_traces[0].x)}개 노드"
print(f"5) 그래프 렌더 OK: 15개 중 {len(node_traces[0].x)}개 노드만 표시")

# 노드 크기가 전부 같은지 (근거 수로 크기를 주지 않는다는 원칙 B)
assert isinstance(node_traces[0].marker.size, (int, float)), "노드 크기가 개수에 따라 달라짐"
print(f"6) 노드 크기 균일 OK (원칙 B — 근거 수를 크기로 집계하지 않음)")

# 7) 근거 표 행 생성 — 6번째 원소(relationship_type)로 소스 판정
detail = []
for cp, g in grouped:
    for dt, headline, url, status, context, rel_type in g["headlines"]:
        detail.append(("SEC 공시" if rel_type == "공시상 언급" else "뉴스", url, context or headline))
assert len(detail) == len(edges), f"근거 표 행 수 불일치: {len(detail)} vs {len(edges)}"
assert all(u for _, u, _ in detail), "원문 링크가 빠진 행 있음"
news_rows = sum(1 for s, _, _ in detail if s == "뉴스")
print(f"7) 근거 표 OK: {len(detail)}행 전부 원문 링크 보유 (뉴스 {news_rows}행 / 공시 {len(detail)-news_rows}행)")

# 8) 노드 1개일 때 (0으로 나누기 등 경계)
one = render_relationship_graph_figure("NVDA", "NVIDIA", [edges[0]])
print("8) 노드 1개 경계 케이스 OK")

print("\n전부 통과")

# --- 9) 로고 렌더링 (2026-07-27 추가) ------------------------------------------------
from lib.charts import _NODE_RADIUS, _HUB_RADIUS, _edge_endpoints

# CP03은 일부러 넣는다 — 근거 1건이라 상위 10개에 못 들어 그래프에 노드가 없다.
# 그려지지도 않는 노드의 로고까지 배치하면 안 되므로, 이게 걸러지는지 확인하는 게 목적이다.
drawn = [cp for cp, _ in grouped[:MAX_RELATIONSHIP_NODES]]
assert "CP00" in drawn and "CP03" not in drawn, f"테스트 전제가 깨짐: {drawn}"

logos = {"CP00": "https://logo/cp00.png", "CP03": "https://logo/cp03.png",
         "NVDA": "https://logo/nvda.png"}
fig_logo = render_relationship_graph_figure("NVDA", "NVIDIA Corporation", edges, logos=logos)

imgs = fig_logo.layout.images
assert len(imgs) == 2, f"로고 이미지 수 불일치: {len(imgs)} (허브 NVDA + 노드 CP00 = 2여야 함)"
print(f"\n9) 로고 {len(imgs)}개 배치 OK — 허브 + 그려진 노드만, "
      f"그래프에 없는 CP03은 로고를 줘도 무시됨")

# 로고가 원 안에 들어가는지 — 정사각형이 원에 내접하려면 한 변 <= 반지름 x 2/√2
import math as _m
for im in imgs:
    r = _HUB_RADIUS if (im.x == 0 and im.y == 0) else _NODE_RADIUS
    half_diag = (im.sizex / 2) * _m.sqrt(2)
    assert half_diag <= r * 1.05, f"로고가 원 밖으로 삐져나감: 대각 반지름 {half_diag:.3f} > 원 {r:.3f}"
    assert im.sizing == "contain", "비율 보존(sizing=contain)이 안 걸림"
    assert im.xanchor == "center" and im.yanchor == "middle", "로고가 중앙 정렬이 아님"
print(f"10) 모든 로고가 원 안에 내접·중앙정렬·비율보존 OK")

# 원이 데이터 좌표 shape으로 그려졌는지 (로고와 같은 좌표계여야 창 크기 변화에 같이 움직임)
circles = [s for s in fig_logo.layout.shapes if s.type == "circle"]
assert len(circles) >= 10, f"노드 원 shape이 부족: {len(circles)}"
assert all(s.xref == "x" and s.yref == "y" for s in circles), "원이 데이터 좌표가 아님"
print(f"11) 노드 원 {len(circles)}개가 데이터 좌표 shape OK (로고와 같은 좌표계)")

# 선이 원 테두리에서 끊기는지 (중심까지 그으면 로고 위로 선이 지나간다)
(sx, sy), (ex, ey) = _edge_endpoints(1.0, 0.0)
assert abs(sx - _HUB_RADIUS) < 1e-9, f"선이 허브 중심에서 시작함: {sx}"
assert abs(ex - (1.0 - _NODE_RADIUS)) < 1e-9, f"선이 노드 중심까지 감: {ex}"
print(f"12) 선이 원 테두리에서 시작/종료 OK (허브 {sx:.3f} → 노드 {ex:.3f}, 중심 관통 안 함)")

# 로고 없이 호출해도 (기존 동작) 깨지지 않는지 — 폴백 경로
fig_none = render_relationship_graph_figure("NVDA", "NVIDIA", edges)
assert len(fig_none.layout.images) == 0, "로고를 안 넘겼는데 이미지가 생김"
assert len([s for s in fig_none.layout.shapes if s.type == "circle"]) >= 10
print("13) 로고 없을 때 폴백(빈 원) OK — 이미지 0개, 원은 그대로")

print("\n로고 관련 전부 통과")
