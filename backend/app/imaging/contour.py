"""Trace the outline polygons (with holes) of a binary mask, in mask pixel coordinates.

Pure Python over boundary pixels only, so it stays fast without numpy/OpenCV. The mask is
downsampled to at most `max_side` pixels on its long side before tracing; the result is
scaled back, so outlines are display-quality rather than pixel-exact.
"""

from __future__ import annotations

from collections import defaultdict

from PIL import Image, ImageChops, ImageFilter

Point = tuple[float, float]
Ring = list[Point]


def _simplify(points: Ring, eps: float) -> Ring:
    """Douglas-Peucker on a closed ring (first == last)."""
    if len(points) <= 4 or eps <= 0:
        return points

    def dp(pts: Ring) -> Ring:
        if len(pts) < 3:
            return pts
        (x0, y0), (x1, y1) = pts[0], pts[-1]
        dx, dy = x1 - x0, y1 - y0
        norm = (dx * dx + dy * dy) ** 0.5
        best_i, best_d = -1, -1.0
        for i in range(1, len(pts) - 1):
            x, y = pts[i]
            d = abs(dy * (x - x0) - dx * (y - y0)) / norm if norm else ((x - x0) ** 2 + (y - y0) ** 2) ** 0.5
            if d > best_d:
                best_i, best_d = i, d
        if best_d > eps:
            left = dp(pts[: best_i + 1])
            right = dp(pts[best_i:])
            return left[:-1] + right
        return [pts[0], pts[-1]]

    # Split at the farthest point from the start so the closed ring simplifies well.
    far = max(range(len(points) - 1), key=lambda i: (points[i][0] - points[0][0]) ** 2 + (points[i][1] - points[0][1]) ** 2)
    a = dp(points[: far + 1])
    b = dp(points[far:])
    out = a[:-1] + b
    if out[0] != out[-1]:
        out.append(out[0])
    return out


def _signed_area(ring: Ring) -> float:
    s = 0.0
    for i in range(len(ring) - 1):
        x0, y0 = ring[i]
        x1, y1 = ring[i + 1]
        s += x0 * y1 - x1 * y0
    return s / 2.0


def _point_in_ring(pt: Point, ring: Ring) -> bool:
    x, y = pt
    inside = False
    j = len(ring) - 2
    for i in range(len(ring) - 1):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def trace_outlines(mask: Image.Image, *, max_side: int = 512, simplify_px: float = 1.2, min_area_px: float = 4.0) -> list[list[Ring]]:
    """Return polygons as [outer, hole, hole, ...] rings in ORIGINAL mask pixel coordinates."""
    m = mask.convert("L")
    scale = 1.0
    if max(m.size) > max_side:
        scale = max(m.size) / max_side
        m = m.resize((max(1, round(m.width / scale)), max(1, round(m.height / scale))), Image.BOX)
    m = m.point(lambda v: 255 if v >= 128 else 0)
    w, h = m.size
    data = m.tobytes()
    boundary = ImageChops.difference(m, m.filter(ImageFilter.MinFilter(3)))
    # MinFilter treats the border as replicated; force pixels on the image edge to be boundary.
    bbox = m.getbbox()
    if not bbox:
        return []
    bdata = bytearray(boundary.tobytes())
    for x in range(w):
        bdata[x] = data[x]
        bdata[(h - 1) * w + x] = data[(h - 1) * w + x]
    for y in range(h):
        bdata[y * w] = data[y * w]
        bdata[y * w + w - 1] = data[y * w + w - 1]

    def inside(x: int, y: int) -> bool:
        return 0 <= x < w and 0 <= y < h and data[y * w + x] != 0

    edges: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
    for y in range(bbox[1], bbox[3]):
        row = y * w
        for x in range(bbox[0], bbox[2]):
            if bdata[row + x] == 0 or data[row + x] == 0:
                continue
            if not inside(x, y - 1):
                edges[(x, y)].append((x + 1, y))
            if not inside(x + 1, y):
                edges[(x + 1, y)].append((x + 1, y + 1))
            if not inside(x, y + 1):
                edges[(x + 1, y + 1)].append((x, y + 1))
            if not inside(x - 1, y):
                edges[(x, y + 1)].append((x, y))

    loops: list[Ring] = []
    while edges:
        start = next(iter(edges))
        cur = start
        prev_dir: tuple[int, int] | None = None
        loop: Ring = [cur]
        while True:
            outs = edges.get(cur)
            if not outs:
                break
            if len(outs) == 1 or prev_dir is None:
                nxt = outs.pop(0)
            else:
                # Prefer the right turn (clockwise in image coords), then straight, then left,
                # so two regions touching at a corner stay separate loops.
                def rank(p: tuple[int, int]) -> int:
                    dx, dy = p[0] - cur[0], p[1] - cur[1]
                    cross = prev_dir[0] * dy - prev_dir[1] * dx  # type: ignore[index]
                    return 0 if cross > 0 else (1 if cross == 0 else 2)

                outs.sort(key=rank)
                nxt = outs.pop(0)
            if not outs:
                del edges[cur]
            prev_dir = (nxt[0] - cur[0], nxt[1] - cur[1])
            loop.append(nxt)
            cur = nxt
            if cur == start:
                break
        if len(loop) >= 4 and loop[0] == loop[-1]:
            loops.append(loop)

    outers: list[Ring] = []
    holes: list[Ring] = []
    for loop in loops:
        area = _signed_area(loop)
        if abs(area) < min_area_px:
            continue
        simplified = _simplify([(float(x), float(y)) for x, y in loop], simplify_px)
        if len(simplified) < 4:
            continue
        (outers if area > 0 else holes).append(simplified)

    polygons: list[list[Ring]] = [[o] for o in outers]
    for hole in holes:
        best = None
        best_area = float("inf")
        for i, o in enumerate(outers):
            if _point_in_ring(hole[0], o):
                a = abs(_signed_area(o))
                if a < best_area:
                    best, best_area = i, a
        if best is not None:
            polygons[best].append(hole)

    if scale != 1.0:
        polygons = [[[(x * scale, y * scale) for x, y in ring] for ring in poly] for poly in polygons]
    return polygons
