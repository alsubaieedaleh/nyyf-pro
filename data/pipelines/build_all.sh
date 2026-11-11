#!/usr/bin/env bash
# Rebuild all map data. Needs local clones of the two open data mirrors and the old nyyf repo:
#   MOJ_REPO      https://github.com/civillizard/saudi-real-estate-data
#   BOUNDARIES    https://github.com/homaily/Saudi-Arabia-Regions-Cities-and-Districts
#   OLD_NYYF      the old nyyf repo (for the Riyadh land offers). Optional: without it the
#                 committed riyadh-offers.geojson is reused (the offers are frozen).
set -euo pipefail
: "${MOJ_REPO:?}" "${BOUNDARIES:?}"
cd "$(dirname "$0")/../.."
rm -f apps/web/public/data/market-meta.json

# Every city in cities.json (slug, National Address spelling, English name, REGA rental file region).
python3 -c 'import json,sys; [print("|".join((c["slug"], c["ar"], c["en"], c["rent_region"]))) for c in json.load(open(sys.argv[1]))]' \
  data/pipelines/cities.json > "${TMPDIR:-/tmp}/nyyf-cities.txt"
while IFS='|' read -r slug city city_en region; do
  python3 data/pipelines/build_moj_market.py --moj "$MOJ_REPO/moj/sales" \
    --districts "$BOUNDARIES/geojson/districts.geojson" --city "$city" --city-en "$city_en" --slug "$slug"
  python3 data/pipelines/build_rega_rent.py --rent "$MOJ_REPO/rega/quarterlies/rental" \
    --region "$region" --city "$city" --slug "$slug"
done < "${TMPDIR:-/tmp}/nyyf-cities.txt"

if [ -n "${OLD_NYYF:-}" ]; then
  python3 data/pipelines/build_riyadh_offers.py "$OLD_NYYF/Web/muqayyim/src/assets"
fi

# Plans need the district prices (and, for Riyadh, the offers) built above.
while IFS='|' read -r slug city _ _; do
  python3 data/pipelines/build_plans.py --moj "$MOJ_REPO/moj/sales" --slug "$slug" --city "$city"
done < "${TMPDIR:-/tmp}/nyyf-cities.txt"
