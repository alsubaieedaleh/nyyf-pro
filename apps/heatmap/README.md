# Nyyf public price heat map

A free, public map of price per m² by district for Riyadh, Jeddah, Makkah, Madinah, Dammam and Al Khobar.
Its job is to bring people in: brokers, buyers and owners check their district, share the link, and later
meet Nyyf Pro. Districts only; plans (مخططات), parcels and the old offers stay in Nyyf Pro.

- Static site: Vite + TypeScript + MapLibre GL, no server and no database.
- Basemap: OpenFreeMap Positron (free, no key, commercial use allowed with attribution).
- Data: `public/data/districts.geojson` (about 770 KB, 185 KB gzipped) and `public/data/meta.json`,
  written by `data/pipelines/export_public.py` from the final dataset.
- Arabic first (RTL), English toggle. Mobile bottom sheet, desktop side panel. Deep links: `#riyadh/<district id>`.

## What the map shows

| Element | Meaning |
|---|---|
| Fill colour | Price per m², five steps from teal (low) to coral (high). Breaks are the quintiles of each city's priced districts, so colours compare districts inside a city |
| Fill strength | Confidence: high is solid, medium lighter, low paler |
| Grey | No price: too few deals in 24 months |
| Panel | Price, confidence label and its reason, typical range (25th to 75th percentile), year-on-year change, deals in 12 months, last deal, apartment rent per m² |

## Run it

```bash
pnpm install
pnpm --filter @nyyf/heatmap dev      # http://localhost:5173
pnpm --filter @nyyf/heatmap build    # static site in apps/heatmap/dist
```

## Data pipeline (automatic, about $0)

`.github/workflows/heatmap-data.yml` runs every Sunday at 06:00 Riyadh time (and by hand from the Actions tab):

1. Shallow-clones the MOJ/REGA open data mirror and the district boundaries.
2. Runs `build_all.sh`, `build_base.py` and `build_final.py` (the same scripts as the full dataset; about 3 minutes).
3. Runs `export_public.py`, which keeps district rows only and checks the quality gates against the data
   that is live now: priced districts may not fall by more than 5% in a city, a city's median may not move
   by more than 15%, and every district needs a name and a sane range. A failed gate fails the run, GitHub
   emails the owner, and the live data stays as it was. `force` on a manual run publishes anyway.
4. Commits `apps/heatmap/public/data` only when the numbers changed, then calls the deploy workflow.

`.github/workflows/heatmap-deploy.yml` builds the site on every change (and checks it on pull requests).
It publishes to GitHub Pages only when the repository variable `HEATMAP_PUBLISH` is `true`.

Cost: GitHub Actions and Pages are free for a public repository, OpenFreeMap is free. A custom domain is the
only optional cost. If traffic outgrows Pages (soft limit 100 GB a month), the same `dist/` folder deploys to
Cloudflare Pages unchanged (`public/_headers` already sets its caching).

## Going live (checklist)

1. Clear the open questions under "Licensing" below.
2. Settings > Pages > Source: **GitHub Actions**.
3. Settings > Secrets and variables > Actions > Variables: `HEATMAP_PUBLISH = true`.
   Optional: `HEATMAP_WAITLIST_URL` (shows the "Nyyf Pro for brokers" card in the district panel),
   `HEATMAP_CF_BEACON` (Cloudflare Web Analytics token, cookie-free visitor counts).
4. Run "Heat map deploy" from the Actions tab. The site is at `https://<owner>.github.io/nyyf-pro/`
   (or a custom domain set in Settings > Pages).

## Room for revenue later

The public map is the free tier. Hooks already in place: the Pro card (`HEATMAP_WAITLIST_URL`) in every district
panel, shareable deep links, and analytics. Natural paid steps, all from the Nyyf Pro plan:

- Accounts and a watchlist with price alerts per district (needs a small backend, e.g. Supabase free tier).
- Pro: plan (مخطط) and parcel prices, instant valuation with comparables, deal lists, PDF reports.
- Broker branding on shared links and reports; an API for developers and banks.

## Licensing (check before going public)

| Data | Licence | Status |
|---|---|---|
| MOJ deals | KSA Open Data License: reuse, derivatives and redistribution allowed with attribution to the Ministry of Justice; do not present derived numbers as official | OK with the attribution and disclaimer on the map. MOJ also asks that its raw data is not modified: we publish our own medians, labelled as estimates |
| REGA rents | KSA Open Data License, attribute REGA | OK |
| Source mirror | `civillizard/saudi-real-estate-data` (MIT code, raw government files unchanged) | Works, but a community mirror could stop updating; move the fetch to open.data.gov.sa when possible |
| District polygons | GPL-2.0 repository whose README says it was collected from maps.address.gov.sa (SPL National Address) | **Open question.** GPL lets us republish the derived polygons (credited, same licence), but the original rights sit with SPL, whose terms may not allow redistribution, and a paid tier makes this weigh more. Options: ask SPL, licence the National Address API, or switch to official boundaries |
| Basemap | OpenFreeMap / OpenStreetMap (ODbL) | OK, attribution shown on the map |
| Old offers | Scraped listings, not for republishing | Not used by this map. Note: they are in `apps/web/public/data` in this public repo |
