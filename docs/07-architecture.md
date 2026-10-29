# 07 · Architecture

## Recommended stack

| Layer | Choice | Why |
|---|---|---|
| Web app | **Next.js (React, TypeScript)** + Tailwind + shadcn/ui | Largest ecosystem for map UIs, SSR for shareable report and listing pages (SEO, fast WhatsApp previews), RTL works well |
| Map | **MapLibre GL JS** (open source fork of Mapbox GL) | Same API the old app used, no per-load Mapbox fees, full vector tile and style control. Basemap from MapTiler or self-hosted Protomaps |
| Mobile | **PWA first**, then **React Native + MapLibre Native** (or Expo) in Phase 3 | One codebase family with the web; the old Flutter app is only API stubs so little is lost |
| API | **TypeScript (NestJS or Fastify)** | Same language as the front end, typed contracts shared with the client |
| Valuation service | **Python FastAPI** + LightGBM/XGBoost | Python stays where ML lives; replaces Flask + Keras |
| Database | **PostgreSQL 16 + PostGIS + H3** | Spatial queries, row-level security, one store for everything |
| Vector tiles | Static layers (districts, plans, parcels) → **PMTiles** on a CDN; dynamic layers (deals, listings) → **Martin** tile server from PostGIS behind CDN cache | This is what makes the map smooth |
| Jobs | Scheduled workers (BullMQ or a cron container) | Nightly deal ingest, stats rollup, alert matching, model retraining |
| Auth | Phone OTP (Unifonic or Taqnyat SMS), Google, Apple; JWT with rotating signed keys | Saudi brokers live on their phones |
| Files | S3-compatible storage + image CDN | Listing photos, report PDFs |
| PDF | Headless Chromium rendering the same report page | One design for web and PDF |
| Payments | Moyasar or Tap | Local cards, mada, Apple Pay |
| Hosting | AWS **me-central-1 (UAE)** or a Saudi region provider (e.g. AWS Saudi region if live, Oracle Jeddah, STC Cloud) | Latency, and Saudi data residency rules (PDPL) for personal data |
| Observability | Sentry, OpenTelemetry, uptime checks | |

Alternative if the user prefers to stay on Angular: Angular 18+ with MapLibre works; the rest of the stack is unchanged. This is listed as an open decision in 09.

## Service diagram

```
               ┌────────────── CDN (tiles, images, static) ───────────────┐
 Browser/PWA ──┤                                                          │
 Mobile app ───┤── Next.js web (SSR pages, report/listing share pages)    │
               │── API (TypeScript) ── PostgreSQL + PostGIS (RLS)         │
               │        │                  ▲        ▲                      │
               │        ├─ Valuation (FastAPI, model registry)             │
               │        └─ Queue ── Workers: ingest · stats · alerts · PDF │
               │── Martin tile server (deals, listings MVT) ───────────────┘
               └── PMTiles (districts, plans, parcels)
```

## Valuation engine v2

1. **Comparables first.** For a target point, find deals within the same plan, then district, then radius, weighted by distance, recency, area similarity, and property type. Time-adjust each comparable with the district's monthly index.
2. **Model second.** Gradient boosted model on: lat/lng, H3 cell, district and plan target encodings, area (log), property type, street width, frontage, corner flag, months since deal, district index. Train on MOJ deals; evaluate on a time-based holdout.
3. **Blend and explain.** Final estimate = weighted blend of comparables estimate and model. Range from quantile models (P10 to P90). Confidence from comparable count and spread. Return top comparables with their adjustments.
4. **Versioned.** Every valuation stores `model_version`; feedback with actual prices feeds retraining.

## Security baseline (fixes the audit findings)
- No secrets in code. Environment variables via a secrets manager; rotate the old Azure Postgres password and Mapbox token.
- Parameterised queries only (ORM or query builder such as Drizzle or Kysely). No string-built SQL.
- Persistent JWT signing keys with rotation; short access tokens plus refresh tokens.
- Row-level security on all office data.
- Rate limiting on OTP, valuation, and tile endpoints.
- Terraform state in a remote encrypted backend, never in git.
- PDPL compliance: consent, data residency, data export and delete (the old "delete my account" stays).

## Repository layout (monorepo, pnpm + Turborepo)

```
nyyf-pro/
  apps/web          Next.js app
  apps/api          TypeScript API
  apps/mobile       React Native (Phase 3)
  services/valuation  FastAPI + model training
  services/tiles    Martin config, PMTiles build scripts
  packages/ui       shared components and map styles
  packages/types    shared API types
  data/pipelines    ingest and cleaning jobs
  infra/            Terraform
  docs/             copy of this source of truth
```
