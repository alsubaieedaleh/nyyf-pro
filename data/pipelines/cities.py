"""Cities the pipeline tries. cities.json is the single list for the scripts and the site.

A city is built when it is listed here; export_public.py then publishes it only if enough of its districts get a
confident price (see MIN_CONFIDENT there).
"""

import json
from pathlib import Path

CITY_LIST = json.loads((Path(__file__).with_name("cities.json")).read_text(encoding="utf-8"))
CITY_AR = {c["slug"]: c["ar"] for c in CITY_LIST}
