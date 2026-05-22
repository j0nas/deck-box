#!/usr/bin/env bash
# Regenerate Voronoi scale data, then render the combined base/lid STLs.
set -euo pipefail

cd "$(dirname "$0")"
source .venv/bin/activate

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
