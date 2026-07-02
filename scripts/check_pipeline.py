"""Sanity check: ensure modules import and key callables exist."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

REQUIRED = {
    "sheet_io": ["dump", "apply", "normalize_url", "extract_img_urls", "build_description_html"],
    "nano_gen": ["clean", "get_api_key"],
    "edit_gen": ["edit", "get_api_key"],
    "agnes_gen": ["clean", "build_prompt", "get_api_key"],
    "fetch_image": ["fetch", "normalize_url"],
    "run_pipeline": ["prepare", "finalize"],
}

problems = []
for mod, names in REQUIRED.items():
    try:
        m = importlib.import_module(mod)
    except Exception as e:  # noqa: BLE001
        problems.append(f"import {mod} failed: {e}")
        continue
    for n in names:
        if not hasattr(m, n):
            problems.append(f"{mod}.{n} missing")

if problems:
    print("FAIL")
    for p in problems:
        print("  -", p)
    sys.exit(1)
print("OK: all modules import, all required callables present")
