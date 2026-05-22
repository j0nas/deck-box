// MTG EDH deck box — OpenSCAD / Manifold parametric model.
//
// Coordinate convention:
//   z = 0 is the cards-cavity floor.
//   Base bottom at z = -FLOOR_T (negative).
//   Cards cavity top at z = CAV_H.
//   Lid top at z = CAV_H + CEILING_T.
//
// Build:
//   python seam.py                                          # regenerate Voronoi data
//   openscad --backend=Manifold -o base.stl     -D 'mode="base"'     deckbox.scad
//   openscad --backend=Manifold -o lid.stl      -D 'mode="lid"'      deckbox.scad
//   openscad --backend=Manifold -o assembly.png \
//        --imgsize=1600,1200 --colorscheme=Tomorrow \
//        -D 'mode="assembly"' deckbox.scad

include <seam.scad>

// === Parameters (mm) =========================================================

// Cavity sized for sleeved cards 68.3 × 91.3 mm + 3 mm total clearance per
// horizontal axis (1.5 mm per side) and an 80 mm card stack + 1 mm vertical
// slack so the top card slides in cleanly.
CAV_W = 94.3;          // cards cavity inner width  (X) — card 91.3 + 3
CAV_D = 71.3;          // cards cavity inner depth  (Y) — card 68.3 + 3
CAV_H = 81.0;          // cards cavity inner height (Z) — deck 80 + 1
CAV_R = 3.92;          // cavity vertical corner radius

WIDE_WALL_T   = 3.92;  // base wide-section wall thickness
NARROW_WALL_T = 1.86;  // narrow section / lid wall thickness
FLOOR_T       = 1.86;  // base bottom thickness
CEILING_T     = 1.86;  // lid top thickness

SEAM_Z        = 20.0;  // base shoulder height above cavity floor
VERTICAL_GAP  = 1.5;   // visible vertical gap between base top and lid bottom
LID_BOTTOM_Z  = SEAM_Z + VERTICAL_GAP;  // 21.5

H_TOL = 0.4;           // horizontal print tolerance (lid cavity larger per side)

// Decorative window dimensions — sized to preserve a 5.8 mm frame border
// on each side of the cavity (so WIN = CAV − 11.6).
WIN_W = 82.7;
WIN_D = 59.7;
WIN_R = 2.5;

// === Derived =================================================================

BOX_W       = CAV_W + 2 * WIDE_WALL_T;       // 100.84
BOX_D       = CAV_D + 2 * WIDE_WALL_T;       // 75.84
NARROW_W    = CAV_W + 2 * NARROW_WALL_T;     // 96.72
NARROW_D    = CAV_D + 2 * NARROW_WALL_T;     // 71.72
LID_CAV_W   = NARROW_W + 2 * H_TOL;          // 97.32
LID_CAV_D   = NARROW_D + 2 * H_TOL;          // 72.32

BASE_BOT_Z  = -FLOOR_T;                      // -1.86
LID_TOP_Z   = CAV_H + CEILING_T;             // 72.86

// Outer fillet radii — uniform wall thickness around the corners.
WIDE_OUTER_R   = CAV_R + WIDE_WALL_T;        // 7.84
NARROW_OUTER_R = CAV_R + NARROW_WALL_T;      // 5.78
LID_CAV_R      = NARROW_OUTER_R + H_TOL;     // 6.08
LID_OUTER_R    = WIDE_OUTER_R;               // 7.84

$fn = 36;   // facet count for circles/cylinders

// === Helper modules ==========================================================

// 2D rounded rectangle (hull of 4 corner circles, all of radius r)
module rounded_rect(w, d, r) {
    hull() {
        translate([ r - w/2,  r - d/2]) circle(r=r);
        translate([ w/2 - r,  r - d/2]) circle(r=r);
        translate([ r - w/2,  d/2 - r]) circle(r=r);
        translate([ w/2 - r,  d/2 - r]) circle(r=r);
    }
}

// 3D rounded box, extruded along Z from z_bot upward by h.
module rounded_box(w, d, h, r, z_bot=0) {
    translate([0, 0, z_bot])
        linear_extrude(height=h)
            rounded_rect(w, d, r);
}

// Through-hole window: cuts a rounded rectangle through the full extent.
module window_cut(w, d, h, r, z_bot) {
    rounded_box(w, d, h, r, z_bot);
}

// === Parts ===================================================================

// (Scales now PROTRUDE from a smooth wall — no shell carve needed.)

// Snap-fit locking bumps: small spheres on the narrow section's outer wall
// at LOCK_BUMP_Z. The lid has matching spherical cavities — when assembled,
// the lid flexes slightly over the bumps and clicks into place.
LOCK_BUMP_R   = 0.7;    // bump protrusion radius (mm)
LOCK_CAV_R    = 1.0;    // matching cavity radius (gives ~0.3mm play once snapped)
LOCK_BUMP_Z   = (SEAM_Z + CAV_H) / 2;  // mid-height of the narrow section (≈45)

// One bump per LONG side only (at y = ±NARROW_D/2). Squeezing the short
// (unbumped) sides bows the long sides outward at their midpoints, popping
// the bumps free of their cavities — that's the lid-release motion.
module lock_bumps() {
    translate([0, -NARROW_D/2, LOCK_BUMP_Z]) sphere(r=LOCK_BUMP_R);
    translate([0, +NARROW_D/2, LOCK_BUMP_Z]) sphere(r=LOCK_BUMP_R);
}

module lock_cavities() {
    translate([0, -NARROW_D/2, LOCK_BUMP_Z]) sphere(r=LOCK_CAV_R);
    translate([0, +NARROW_D/2, LOCK_BUMP_Z]) sphere(r=LOCK_CAV_R);
}

// Base body: smooth outer wall + protruding Voronoi scales.
module base() {
    union() {
        difference() {
            union() {
                rounded_box(BOX_W, BOX_D, SEAM_Z - BASE_BOT_Z, WIDE_OUTER_R, BASE_BOT_Z);
                rounded_box(NARROW_W, NARROW_D, CAV_H - SEAM_Z, NARROW_OUTER_R, SEAM_Z);
                lock_bumps();
            }
            rounded_box(CAV_W, CAV_D, CAV_H + 0.5, CAV_R, 0);
            window_cut(WIN_W, WIN_D, FLOOR_T + 1.0, WIN_R, BASE_BOT_Z - 0.5);
        }
        // base_teeth is already clipped to z ≤ SEAM_Z in seam.py.
        base_teeth();
    }
}

// Lid body: smooth outer wall + protruding Voronoi scales.
module lid() {
    union() {
        difference() {
            rounded_box(BOX_W, BOX_D, LID_TOP_Z - LID_BOTTOM_Z, LID_OUTER_R, LID_BOTTOM_Z);
            rounded_box(LID_CAV_W, LID_CAV_D, CAV_H - LID_BOTTOM_Z + 0.01, LID_CAV_R, LID_BOTTOM_Z);
            window_cut(WIN_W, WIN_D, CEILING_T + 1.0, WIN_R, CAV_H - 0.5);
            lock_cavities();
        }
        // lid_teeth is already clipped to [LID_BOTTOM_Z, LID_TOP_Z] in seam.py.
        lid_teeth();
    }
}

// === Entry point — render based on `mode` variable ===========================

mode = "assembly";   // override with -D 'mode="base"' or 'mode="lid"'

if (mode == "base") {
    base();
} else if (mode == "lid") {
    lid();
} else if (mode == "exploded") {
    color("burlywood") base();
    translate([0, 0, 30]) color("steelblue") lid();
} else {
    color("burlywood") base();
    color("steelblue") lid();
}
