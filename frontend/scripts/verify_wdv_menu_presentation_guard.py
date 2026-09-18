#!/usr/bin/env python3
from pathlib import Path
import re

WLV=Path.home()/"Applications"/"MultiViewer"/"Well-Log-Viewer"/"frontend"
CSS=WLV/"src/styles/track-layout-prototype.css"

if not CSS.is_file():
    raise SystemExit(f"FAIL WDV MENU PRESENTATION GUARD: missing {CSS}")

css=CSS.read_text()
required={
    "toolbar shell":"WDV MENU / TOOLBAR PRESENTATION REGRESSION RESTORE V1.0.0",
    "toolbar background":"background: #202124;",
    "toolbar button transparent":"background: transparent;",
    "inventory dark background":"background: #080a0d;",
    "inventory hover":"background: #11151a;",
    "inventory control dark":"background: #0b0e12;",
    "panel heading":"background: #1e1e1e;",
    "right/search controls":"background: #171717;",
}
for label,needle in required.items():
    if needle not in css:
        raise SystemExit(f"FAIL WDV MENU PRESENTATION GUARD: {label} missing ({needle})")

print("PASS WDV MENU PRESENTATION GUARD")
print("Toolbar accepted dark presentation: PRESENT")
print("Inventory accordion accepted dark presentation: PRESENT")
print("Inventory/search controls accepted dark presentation: PRESENT")
