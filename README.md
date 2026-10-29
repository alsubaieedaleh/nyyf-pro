# Nyyf Pro

Map-first workspace for Saudi real estate brokers. The prototype covers Riyadh, Jeddah, Makkah,
Madinah, Dammam and Al Khobar.

The product source of truth lives in [`docs/`](docs/README.md): vision, personas, features,
map spec, data model, architecture, and roadmap. Change the docs before changing the plan.

## Layout

```
apps/web            Next.js web app + PWA (the map)
apps/api            TypeScript API (Phase 1, not started)
services/valuation  Python valuation engine (Phase 1, not started)
data/pipelines      Data preparation scripts
docs/               Source of truth
```

## Run the map prototype

```bash
pnpm install
cp .env.example apps/web/.env.local   # optional, the default basemap needs no key
pnpm dev                              # http://localhost:3000
```

## Rebuild the map data

The map shows sold prices from Ministry of Justice deals and rents from REGA (Ejar) per district,
on National Address district boundaries. Riyadh also shows ~17.5k old land offers (asking prices)
from the old nyyf repo. Sources, licenses, freshness and gaps: [`docs/10-data-sources.md`](docs/10-data-sources.md).

```bash
pip install shapely
git clone https://github.com/civillizard/saudi-real-estate-data   # MOJ + REGA open data mirror
git clone https://github.com/homaily/Saudi-Arabia-Regions-Cities-and-Districts
MOJ_REPO=<saudi-real-estate-data> BOUNDARIES=<Saudi-Arabia-Regions-Cities-and-Districts> \
OLD_NYYF=<old nyyf repo> data/pipelines/build_all.sh
```

`build_all.sh` runs, per city, `build_moj_market.py` (sold prices, trends, recent deals) and
`build_rega_rent.py` (rents), then `build_riyadh_offers.py` (old Riyadh offers). Output goes to
`apps/web/public/data/`.
