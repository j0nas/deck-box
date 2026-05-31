#!/usr/bin/env bash
# Regenerate Voronoi scale data, then render the combined base/lid STLs.
# Pass --step to additionally produce an assembled BRep STEP file via FreeCAD
# (slow: ~9 min, requires FreeCAD installed at /Applications/FreeCAD.app).
set -euo pipefail

cd "$(dirname "$0")"
source .venv/bin/activate

WANT_STEP=0
for arg in "$@"; do
    case "$arg" in
        --step) WANT_STEP=1 ;;
        -h|--help)
            echo "usage: $0 [--step]"
            echo "  --step    also export assembly.step (slow, ~9 min, needs FreeCAD)"
            exit 0
            ;;
        *) echo "unknown arg: $arg" >&2; exit 2 ;;
    esac
done

echo ">> Regenerating seam.scad..."
time python seam.py

echo ">> Rendering base.stl + lid.stl..."
time openscad --backend=Manifold -o base.stl -D 'mode="base"' deckbox.scad
time openscad --backend=Manifold -o lid.stl  -D 'mode="lid"'  deckbox.scad

echo ">> Rendering preview PNGs..."
COMMON=( --backend=Manifold --render --imgsize=1600,1200 --colorscheme=Tomorrow )

time openscad "${COMMON[@]}" --camera=0,-150,30,90,0,0,260 \
    -D 'mode="assembly"' -o assembly_side.png deckbox.scad

time openscad "${COMMON[@]}" --camera=0,0,35,55,0,25,200 \
    -D 'mode="assembly"' -o assembly_iso.png deckbox.scad

ls -la base.stl lid.stl assembly_side.png assembly_iso.png

if [ "$WANT_STEP" -eq 1 ]; then
    FREECAD=/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd
    if [ ! -x "$FREECAD" ]; then
        echo ">> --step requested but $FREECAD not found" >&2
        echo "   install with: brew install --cask freecad" >&2
        exit 3
    fi
    echo ">> Exporting assembly.csg from OpenSCAD..."
    time openscad --backend=Manifold -o assembly.csg -D 'mode="assembly"' deckbox.scad
    echo ">> Converting CSG -> STEP via FreeCAD (this takes several minutes)..."
    time "$FREECAD" csg_to_step.py
    ls -la assembly.csg assembly.step
fi
