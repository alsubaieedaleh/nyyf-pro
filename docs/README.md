# Nyyf Pro: Source of Truth

This folder is the single reference for what Nyyf Pro is, who it serves, how it works, and in what order it gets built. When a decision changes, update the relevant file here first, then build.

| # | File | What it answers |
|---|------|-----------------|
| 01 | [01-vision.md](01-vision.md) | Why Nyyf Pro exists, positioning, principles, success metrics |
| 02 | [02-current-state-audit.md](02-current-state-audit.md) | What the old nyyf (Muqayyim) codebase has, what to keep, what to drop |
| 03 | [03-personas-and-jobs.md](03-personas-and-jobs.md) | Broker personas and the jobs they hire the product for |
| 04 | [04-features.md](04-features.md) | Feature set, grouped by module, with priority |
| 05 | [05-map-experience-spec.md](05-map-experience-spec.md) | The headline feature: the smooth, simple data map |
| 06 | [06-data-model.md](06-data-model.md) | Data sources, entities, and the database schema |
| 07 | [07-architecture.md](07-architecture.md) | Tech stack, services, map tile pipeline, security |
| 08 | [08-roadmap.md](08-roadmap.md) | Phased plan with milestones and exit criteria |
| 09 | [09-decisions-and-open-questions.md](09-decisions-and-open-questions.md) | Decisions made, decisions pending, risks |
| 10 | [10-data-sources.md](10-data-sources.md) | Data the prototype runs on: sources, licenses, freshness, coverage, gaps |
| 11 | [11-data-pipeline.md](11-data-pipeline.md) | Data pipeline flow: ingest to publish, confidence, refresh cadence, plugging in future sources |

## One-paragraph summary

Nyyf started as a Riyadh land valuation tool (Angular web, Flutter mobile, Express + Flask/Keras backend). Nyyf Pro turns it into the daily workspace of a Saudi real estate broker: a fast, beautiful map that shows prices, deals, and listings at a glance, wrapped in the tools a broker actually uses every day (instant valuation with comparables, a listings inventory, a client and deal pipeline, and shareable branded reports). The map is the home screen and the product's signature, held to the bar set by the Suhail (سهيل) map at suhail.ai.

## Status

- Created: 2026-10-29
- Stage: Phase 0. Map prototype with real MOJ deals and REGA rents for six cities ([nyyf-pro PR #1](https://github.com/alsubaieedaleh/nyyf-pro/pull/1))
- Owner: da (alsubaieedaleh)
