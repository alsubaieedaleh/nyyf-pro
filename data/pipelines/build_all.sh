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

# slug | city (National Address spelling) | English name | REGA rental file region
while IFS='|' read -r slug city city_en region; do
  python3 data/pipelines/build_moj_market.py --moj "$MOJ_REPO/moj/sales" \
    --districts "$BOUNDARIES/geojson/districts.geojson" --city "$city" --city-en "$city_en" --slug "$slug"
  python3 data/pipelines/build_rega_rent.py --rent "$MOJ_REPO/rega/quarterlies/rental" \
    --region "$region" --city "$city" --slug "$slug"
done <<'CITIES'
riyadh|الرياض|Riyadh|Riyadh
jeddah|جدة|Jeddah|Makkah
makkah|مكة المكرمة|Makkah|Makkah
madinah|المدينة المنورة|Madinah|Madinah
dammam|الدمام|Dammam|EP
khobar|الخبر|Al Khobar|EP
CITIES

if [ -n "${OLD_NYYF:-}" ]; then
  python3 data/pipelines/build_riyadh_offers.py "$OLD_NYYF/Web/muqayyim/src/assets"
fi

# Plans need the district prices (and, for Riyadh, the offers) built above.
for c in riyadh:الرياض jeddah:جدة makkah:"مكة المكرمة" madinah:"المدينة المنورة" dammam:الدمام khobar:الخبر; do
  python3 data/pipelines/build_plans.py --moj "$MOJ_REPO/moj/sales" --slug "${c%%:*}" --city "${c#*:}"
done
