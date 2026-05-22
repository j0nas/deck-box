"""
Generates seam.scad — OpenSCAD include with:
  - Voronoi cell-boundary decorative GROOVES (carved into the wall surface).
  - Cell-shaped INTERLOCKING TEETH: each Voronoi cell becomes a polygonal
    prism. Cells with seed.z > SEAM_Z belong to the LID; below belong to
    the BASE. Lid teeth extend DOWN into the base region, base teeth UP
    into the lid region — they tile the seam band exactly.

Keeps geometry parameters in sync with deckbox.scad. Run:
    python seam.py
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from scipy.spatial import Voronoi
from shapely.geometry import Polygon, box
from shapely.geometry.polygon import orient


# === Parameters — MIRROR deckbox.scad ========================================

CAV_W = 94.3
CAV_D = 71.3
CAV_H = 81.0
CAV_R = 3.92
WIDE_WALL_T = 3.92
NARROW_WALL_T = 1.86
FLOOR_T = 1.86
CEILING_T = 1.86
SEAM_Z = 20.0
VERTICAL_GAP = 1.5
WAVE_AMP = 8.0
LID_BOTTOM_Z = SEAM_Z + VERTICAL_GAP                # 21.5

BOX_W = CAV_W + 2 * WIDE_WALL_T
BOX_D = CAV_D + 2 * WIDE_WALL_T
BASE_BOT_Z = -FLOOR_T
LID_TOP_Z = CAV_H + CEILING_T
WIDE_OUTER_R = CAV_R + WIDE_WALL_T                  # 7.84

# Voronoi cells now cover EVERYTHING — base bottom to PAST the lid top.
# We deliberately overshoot the top so cells fully tile the lid's outer wall
# up to LID_TOP_Z; the lid is intersected with a clipping plane at LID_TOP_Z
# in deckbox.scad to chop the overshoot off cleanly.
CELLS_Z_MIN    = BASE_BOT_Z + 0.01                  # avoid coincident geometry at floor
CELLS_Z_MAX    = LID_TOP_Z + 6.0                    # overshoot the lid top
SEED_Z_MARGIN  = 1.5                                # keep seeds slightly inside the range

# Voronoi seed parameters
SEAM_SEED      = 42
# Target cell density: how many cells per mm² of wall area. Base and lid
# get seed counts proportional to their (perimeter × height) area at this
# density, so visible cell size is the same on both parts.
CELL_DENSITY   = 0.026
ARC_REFINE_LEN = 1.2    # max edge-segment length when discretizing arc-spanning sides

# Protruding scales: cells become outward bumps on a smooth wall.
# Each scale's inner face sits SCALE_OVERLAP inside the wall (for attachment),
# its outer face protrudes SCALE_PROTRUSION beyond the wall outer surface.
# Each cell polygon is shrunk by SCALE_GAP on all sides — that leaves a
# gap of bare smooth wall between adjacent scales, so the scales actually
# read as distinct 3D features (without it, adjacent cells abut and the
# whole surface looks like one offset wall) and the smooth wall behind
# can be painted a contrasting colour.
SCALE_PROTRUSION = 1.5
SCALE_OVERLAP    = 0.3
SCALE_GAP        = 0.4

# Retained for backwards compat with deckbox.scad (seam_band_shell etc.)
TEETH_DEPTH    = SCALE_PROTRUSION + SCALE_OVERLAP   # 1.2 mm total cell thickness

# Aliases retained for compatibility
SEAM_Z_MIN = CELLS_Z_MIN
SEAM_Z_MAX = CELLS_Z_MAX
SEAM_BAND_HALF = (CELLS_Z_MAX - CELLS_Z_MIN) / 2


# === Perimeter walk on the rounded outer profile =============================

def seam_perimeter() -> float:
    R = WIDE_OUTER_R
    return 2 * (BOX_W - 2 * R) + 2 * (BOX_D - 2 * R) + 2 * math.pi * R


def perimeter_xy(s: float, perim: float) -> tuple[float, float, float, float]:
    """Map arc-length s to (wx, wy, odx, ody) on the rounded outer perimeter."""
    R = WIDE_OUTER_R
    L_long = BOX_W - 2 * R
    L_short = BOX_D - 2 * R
    L_arc = math.pi * R / 2
    s = s % perim
    if s < L_long:
        return (-BOX_W/2 + R + s, -BOX_D/2, 0.0, -1.0)
    s -= L_long
    if s < L_arc:
        th = -math.pi/2 + s / R
        return (BOX_W/2 - R + R*math.cos(th), -BOX_D/2 + R + R*math.sin(th),
                math.cos(th), math.sin(th))
    s -= L_arc
    if s < L_short:
        return (BOX_W/2, -BOX_D/2 + R + s, 1.0, 0.0)
    s -= L_short
    if s < L_arc:
        th = s / R
        return (BOX_W/2 - R + R*math.cos(th), BOX_D/2 - R + R*math.sin(th),
                math.cos(th), math.sin(th))
    s -= L_arc
    if s < L_long:
        return (BOX_W/2 - R - s, BOX_D/2, 0.0, 1.0)
    s -= L_long
    if s < L_arc:
        th = math.pi/2 + s / R
        return (-BOX_W/2 + R + R*math.cos(th), BOX_D/2 - R + R*math.sin(th),
                math.cos(th), math.sin(th))
    s -= L_arc
    if s < L_short:
        return (-BOX_W/2, BOX_D/2 - R - s, -1.0, 0.0)
    s -= L_short
    th = math.pi + s / R
    return (-BOX_W/2 + R + R*math.cos(th), -BOX_D/2 + R + R*math.sin(th),
            math.cos(th), math.sin(th))


# === Voronoi seeds (Lloyd-relaxed, wrap-aware) ===============================

def _lloyd_relax(pts: np.ndarray, perim: float, z_lo: float, z_hi: float,
                 iterations: int = 4) -> np.ndarray:
    """Lloyd's relaxation: move each seed toward the centroid of its Voronoi
    cell. Tiled in s to make the perimeter wrap correctly. Clamps z so seeds
    stay in their assigned region (base or lid)."""
    pts = pts.copy()
    for _ in range(iterations):
        tiled = np.vstack([pts + (-perim, 0), pts, pts + (+perim, 0)])
        vor = Voronoi(tiled)
        new = np.empty_like(pts)
        for i in range(len(pts)):
            region = vor.regions[vor.point_region[len(pts) + i]]
            if -1 in region or not region:
                new[i] = pts[i]
                continue
            new[i] = vor.vertices[region].mean(axis=0)
        new[:, 0] = np.mod(new[:, 0], perim)
        new[:, 1] = np.clip(new[:, 1], z_lo, z_hi)
        pts = new
    return pts


def voronoi_seeds() -> np.ndarray:
    """Build the seed set as a union of two independently-distributed clouds
    (base + lid), each sized for CELL_DENSITY × region_area, so the visible
    cell size matches across the seam. Lloyd's relaxation runs per region,
    keeping base seeds below SEAM_Z and lid seeds above LID_BOTTOM_Z."""
    perim = seam_perimeter()
    rng = np.random.default_rng(SEAM_SEED)

    # Seed-allowed z bands, kept slightly inside the cell-allowed ranges so
    # cells naturally extend to the clip lines. Seeds above LID_TOP_Z would
    # generate cells that get fully clipped out, wasting ~8% of the lid
    # budget — keep the upper seed bound at LID_TOP_Z.
    base_lo = BASE_BOT_Z   + SEED_Z_MARGIN
    base_hi = SEAM_Z       - SEED_Z_MARGIN
    lid_lo  = LID_BOTTOM_Z + SEED_Z_MARGIN
    lid_hi  = LID_TOP_Z    - SEED_Z_MARGIN

    n_base = max(1, int(round(CELL_DENSITY * perim * (base_hi - base_lo))))
    n_lid  = max(1, int(round(CELL_DENSITY * perim * (lid_hi  - lid_lo))))

    base_pts = np.column_stack([
        rng.uniform(0, perim, n_base),
        rng.uniform(base_lo, base_hi, n_base),
    ])
    lid_pts = np.column_stack([
        rng.uniform(0, perim, n_lid),
        rng.uniform(lid_lo, lid_hi, n_lid),
    ])
    base_pts = _lloyd_relax(base_pts, perim, base_lo, base_hi)
    lid_pts  = _lloyd_relax(lid_pts,  perim, lid_lo,  lid_hi)
    return np.vstack([base_pts, lid_pts])


def voronoi_with_tiling(pts: np.ndarray):
    """Return scipy Voronoi over the 3x-tiled seed set + phantom seeds far
    above and below the real cell range. The phantoms close the convex hull
    in z so cells at the global top/bottom are bounded (otherwise they have
    `region` with -1 vertices and get skipped — important for the short
    base zone where the rejection rate was ~25% without phantoms).

    Phantoms sit well outside the clip range, so they don't affect any
    geometry we keep — they just give scipy something to terminate the
    cells against."""
    perim = seam_perimeter()
    N = len(pts)
    tiled = np.vstack([pts + (-perim, 0), pts, pts + (+perim, 0)])

    n_phantom = 24
    phantom_s = np.linspace(0, perim, n_phantom, endpoint=False)
    phantom_below = np.column_stack([phantom_s, np.full(n_phantom, CELLS_Z_MIN - 5.0)])
    phantom_above = np.column_stack([phantom_s, np.full(n_phantom, CELLS_Z_MAX + 5.0)])
    phantom = np.vstack([phantom_below, phantom_above])
    phantom_tiled = np.vstack([phantom + (-perim, 0), phantom, phantom + (+perim, 0)])

    all_pts = np.vstack([tiled, phantom_tiled])
    return Voronoi(all_pts), N, perim


def _unused_voronoi_edge_samples(pts: np.ndarray):
    """Legacy: cell-boundary samples for decorative grooves. No longer used."""
    vor, N, perim = voronoi_with_tiling(pts)
    z_lo = BASE_BOT_Z + 0.1
    z_hi = LID_TOP_Z - 2.0
    seen: set[tuple[int, int]] = set()
    for ridge_idx, (a, b) in zip(vor.ridge_vertices, vor.ridge_points):
        if -1 in ridge_idx:
            continue
        ca, cb = a % N, b % N
        if ca == cb:
            continue
        key = (min(ca, cb), max(ca, cb))
        if key in seen:
            continue
        seen.add(key)
        p1 = vor.vertices[ridge_idx[0]]
        p2 = vor.vertices[ridge_idx[1]]
        if max(p1[1], p2[1]) < z_lo or min(p1[1], p2[1]) > z_hi:
            continue
        length = float(np.hypot(p2[0] - p1[0], p2[1] - p1[1]))
        if length < 0.1:
            continue
        n = max(2, int(length / SEAM_EDGE_STEP) + 1)
        for t in np.linspace(0, 1, n):
            s = (p1[0] + t * (p2[0] - p1[0])) % perim
            z = p1[1] + t * (p2[1] - p1[1])
            if z < z_lo - 0.5 or z > z_hi + 0.5:
                continue
            yield s, z


# === Cell polygons (the interlocking teeth) ==================================

def perimeter_arc_starts(perim):
    """Return the s values that mark the start/end of each perimeter arc segment.
    Used to refine polygon edges that cross an arc."""
    R = WIDE_OUTER_R
    L_long = BOX_W - 2 * R
    L_short = BOX_D - 2 * R
    L_arc = math.pi * R / 2
    boundaries = [0.0,
                  L_long,
                  L_long + L_arc,
                  L_long + L_arc + L_short,
                  L_long + L_arc + L_short + L_arc,
                  2*L_long + L_arc + L_short + L_arc,
                  2*L_long + L_arc + L_short + 2*L_arc,
                  2*L_long + L_arc + 2*L_short + 2*L_arc,
                  2*L_long + 2*L_arc + 2*L_short + 2*L_arc]
    return sorted(set(b % perim for b in boundaries))


def refine_polygon_along_perimeter(polygon_2d, perim, max_seg=ARC_REFINE_LEN):
    """For each polygon edge, insert intermediate vertices when:
      - the edge is long (so the chord doesn't deviate too much from the
        actual curved perimeter on arc segments)."""
    refined = []
    n = len(polygon_2d)
    for i in range(n):
        v1 = polygon_2d[i]
        v2 = polygon_2d[(i + 1) % n]
        refined.append(tuple(v1))
        edge_len = float(np.hypot(v2[0] - v1[0], v2[1] - v1[1]))
        steps = int(edge_len / max_seg)
        for j in range(1, steps + 1):
            t = j / (steps + 1)
            refined.append((v1[0] + t * (v2[0] - v1[0]),
                            v1[1] + t * (v2[1] - v1[1])))
    return refined


def line_line_intersect(p1, p2, p3, p4):
    """Intersection of two infinite lines (each given by two points).
    Returns None if parallel."""
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-9:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))


def shrink_voronoi_edges_only(poly: Polygon, gap: float, bounds: tuple) -> Polygon | None:
    """Offset Voronoi-ridge edges of `poly` inward by `gap`. Edges that lie
    on the clipping `bounds` box (the seam clip line, base bottom, etc.) are
    left at the bound — they're not cell-vs-cell boundaries, so they don't
    need a gap. This keeps base scales touching SEAM_Z and lid scales
    touching LID_BOTTOM_Z while still creating inter-cell gaps.

    Shapely's polygon clipping does not guarantee CCW orientation, and the
    inward-normal calculation below assumes CCW (interior on the left of
    each edge). Force CCW up-front."""
    poly = orient(poly, sign=1.0)
    coords = list(poly.exterior.coords)
    if coords[0] == coords[-1]:
        coords = coords[:-1]
    n = len(coords)
    if n < 3:
        return None

    minx, miny, maxx, maxy = bounds
    eps = 1e-4

    def edge_on_clip(p1, p2):
        if abs(p1[1] - miny) < eps and abs(p2[1] - miny) < eps: return True
        if abs(p1[1] - maxy) < eps and abs(p2[1] - maxy) < eps: return True
        if abs(p1[0] - minx) < eps and abs(p2[0] - minx) < eps: return True
        if abs(p1[0] - maxx) < eps and abs(p2[0] - maxx) < eps: return True
        return False

    offset_edges = []
    for i in range(n):
        p1 = coords[i]
        p2 = coords[(i + 1) % n]
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        L = math.hypot(dx, dy)
        if L < 1e-9:
            continue
        if edge_on_clip(p1, p2):
            offset_edges.append((p1, p2))
            continue
        # CCW polygon: interior on the left of each edge → inward normal = (-dy, dx)/L
        nx = -dy / L
        ny = dx / L
        offset_edges.append((
            (p1[0] + nx * gap, p1[1] + ny * gap),
            (p2[0] + nx * gap, p2[1] + ny * gap),
        ))

    m = len(offset_edges)
    if m < 3:
        return None

    new_verts = []
    for i in range(m):
        a1, a2 = offset_edges[i - 1]
        b1, b2 = offset_edges[i]
        pt = line_line_intersect(a1, a2, b1, b2)
        if pt is None:
            pt = b1
        new_verts.append(pt)

    new_poly = Polygon(new_verts)
    if not new_poly.is_valid:
        new_poly = new_poly.buffer(0)
        if new_poly.is_empty or new_poly.geom_type != "Polygon":
            return None
    return new_poly


def cell_polygons(pts: np.ndarray):
    """Yield (cell_idx, polygon_xy_clipped, seed_z, is_lid) for every central seed.

    Scales tile cleanly on a smooth wall:
      - BASE cells clipped to z ≤ SEAM_Z.
      - LID cells clipped to LID_BOTTOM_Z ≤ z ≤ LID_TOP_Z.
    The 1.5 mm gap between SEAM_Z and LID_BOTTOM_Z is the natural print
    clearance for lifting the lid; no cell exists there.

    Inter-cell gaps (SCALE_GAP) are applied only to Voronoi-ridge edges,
    NOT to edges sitting on the seam clip line — that way the BASE scales
    reach all the way up to SEAM_Z and LID scales all the way down to
    LID_BOTTOM_Z, leaving only the intentional VERTICAL_GAP at the seam."""
    vor, N, perim = voronoi_with_tiling(pts)
    base_bounds_box = box(-perim, CELLS_Z_MIN,        2 * perim, SEAM_Z)
    lid_bounds_box  = box(-perim, LID_BOTTOM_Z,       2 * perim, LID_TOP_Z)
    base_extent = base_bounds_box.bounds
    lid_extent  = lid_bounds_box.bounds

    for i in range(N):
        region_idx = vor.point_region[N + i]
        region = vor.regions[region_idx]
        if -1 in region or not region:
            continue
        verts = vor.vertices[region]
        poly = Polygon(verts)
        if not poly.is_valid or poly.area < 0.05:
            continue
        seed_z = pts[i, 1]
        is_lid = seed_z > SEAM_Z
        bounds_box = lid_bounds_box if is_lid else base_bounds_box
        bounds_extent = lid_extent if is_lid else base_extent
        clipped = poly.intersection(bounds_box)
        if clipped.is_empty or clipped.geom_type != "Polygon" or clipped.area < 0.05:
            continue
        shrunk = shrink_voronoi_edges_only(clipped, SCALE_GAP, bounds_extent)
        if shrunk is None or shrunk.area < 0.05 or shrunk.geom_type != "Polygon":
            continue
        ring = list(shrunk.exterior.coords)[:-1]
        if not Polygon(ring).exterior.is_ccw:
            ring = ring[::-1]
        yield i, ring, seed_z, is_lid


def polyhedron_for_cell(polygon_2d, perim) -> tuple[list, list]:
    """Build a 3D polyhedron (points, faces) for the cell polygon as an
    OUTWARD-PROTRUDING SCALE.

    Outer face: protrudes SCALE_PROTRUSION beyond the wall outer surface.
    Inner face: sits SCALE_OVERLAP inside the wall material — gives the
    union with the main body enough overlap to be reliably manifold."""
    refined = refine_polygon_along_perimeter(polygon_2d, perim)
    n = len(refined)
    outer, inner = [], []
    for s, z in refined:
        wx, wy, odx, ody = perimeter_xy(s, perim)
        # Outer face protrudes outward by SCALE_PROTRUSION
        outer.append((wx + odx * SCALE_PROTRUSION, wy + ody * SCALE_PROTRUSION, z))
        # Inner face sits SCALE_OVERLAP inward of the wall outer (so the scale
        # has material that overlaps with the smooth wall, attaching it).
        inner.append((wx - odx * SCALE_OVERLAP, wy - ody * SCALE_OVERLAP, z))
    points = outer + inner
    outer_face = list(range(n))
    inner_face = list(range(2*n - 1, n - 1, -1))
    side_faces = []
    for i in range(n):
        j = (i + 1) % n
        side_faces.append([i, j, j + n, i + n])
    return points, [outer_face, inner_face] + side_faces


# === Emit seam.scad ==========================================================

def fmt_pt(p):
    return f"[{p[0]:.4f},{p[1]:.4f},{p[2]:.4f}]"


def fmt_face(f):
    return "[" + ",".join(str(x) for x in f) + "]"


def emit_polyhedron(points, faces, indent="    ") -> str:
    pts = ",\n".join(f"{indent}  {fmt_pt(p)}" for p in points)
    fcs = ",\n".join(f"{indent}  {fmt_face(f)}" for f in faces)
    return (
        f"{indent}polyhedron(\n"
        f"{indent}  points = [\n{pts}\n{indent}  ],\n"
        f"{indent}  faces = [\n{fcs}\n{indent}  ],\n"
        f"{indent}  convexity = 4\n"
        f"{indent});"
    )


def main():
    pts = voronoi_seeds()
    perim = seam_perimeter()

    base_polys = []
    lid_polys = []
    skipped = 0
    for cell_idx, ring, seed_z, is_lid in cell_polygons(pts):
        try:
            points, faces = polyhedron_for_cell(ring, perim)
        except Exception:
            skipped += 1
            continue
        scad = emit_polyhedron(points, faces)
        (lid_polys if is_lid else base_polys).append(scad)

    out = [
        "// Auto-generated by seam.py — do not edit by hand.",
        "",
        f"SCALE_PROTRUSION = {SCALE_PROTRUSION};",
        f"SCALE_OVERLAP    = {SCALE_OVERLAP};",
        f"SEAM_Z_MIN = {SEAM_Z_MIN};",
        f"SEAM_Z_MAX = {SEAM_Z_MAX};",
        "",
        "// === Protruding Voronoi scales (cells extrude outward from the wall) ===",
        f"// {len(base_polys)} base scales, {len(lid_polys)} lid scales",
        "module base_teeth() {",
        "  union() {",
        *base_polys,
        "  }",
        "}",
        "",
        "module lid_teeth() {",
        "  union() {",
        *lid_polys,
        "  }",
        "}",
        "",
        "// Decorative grooves are no longer used; stub kept for compat.",
        "module voronoi_cutters() { }",
        "",
    ]

    path = Path(__file__).parent / "seam.scad"
    path.write_text("\n".join(out))
    print(f"Wrote {path}")
    print(f"  Base scales: {len(base_polys)} polyhedra")
    print(f"  Lid scales:  {len(lid_polys)} polyhedra")
    if skipped:
        print(f"  Skipped: {skipped} cells (polyhedron build failure)")


if __name__ == "__main__":
    main()
