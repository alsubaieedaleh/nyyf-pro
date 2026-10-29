# Nyyf Pro

Map-first workspace for Saudi real estate brokers. Riyadh first.

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

## Rebuild the seed data

The prototype uses Riyadh districts and ~17.5k land offers from the old nyyf repo.

```bash
pip install shapely
python data/pipelines/build_riyadh_seed.py <old-repo>/Web/muqayyim/src/assets
```

Seed data note: district prices come from the old nyyf dataset and offers are asking prices,
not sold deals. Ministry of Justice deal data arrives in Phase 1.
