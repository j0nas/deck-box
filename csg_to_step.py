"""Convert an OpenSCAD .csg export into a STEP file via FreeCAD's modules.

Run with FreeCAD's bundled python:
    freecadcmd csg_to_step.py
or:
    /Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd csg_to_step.py
"""
import os
import sys

import FreeCAD  # provided by freecadcmd
import importCSG
import Import as ImportStep  # FreeCAD's STEP I/O module


HERE = os.path.dirname(os.path.abspath(__file__))
CSG_PATH = os.path.join(HERE, "assembly.csg")
STEP_PATH = os.path.join(HERE, "assembly.step")


# freecadcmd does NOT set __name__ == "__main__" — code runs at module top level.

if not os.path.exists(CSG_PATH):
    sys.exit(f"missing {CSG_PATH} — run `openscad -o assembly.csg -D 'mode=\"assembly\"' deckbox.scad` first")

print(f"importing {CSG_PATH}...", flush=True)
importCSG.open(CSG_PATH)
doc = FreeCAD.ActiveDocument

shapes = [o for o in doc.Objects if hasattr(o, "Shape") and o.Shape and not o.Shape.isNull()]
if not shapes:
    sys.exit("no shapes after CSG import")

print(f"exporting {len(shapes)} shape(s) to {STEP_PATH}...", flush=True)
ImportStep.export(shapes, STEP_PATH)
size = os.path.getsize(STEP_PATH)
print(f"wrote {STEP_PATH} ({size / 1024:.1f} KiB)", flush=True)
