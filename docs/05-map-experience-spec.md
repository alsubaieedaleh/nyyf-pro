# 05 · Map experience spec (headline feature)

## Reference: Suhail (suhail.ai)

The bar the user set is the map in **Suhail (سهيل)**, a Saudi real estate data platform (founded 2020, about 26 staff). Based on public descriptions, Suhail shows on an interactive map:

- Master plans (مخططات) and land parcels (قطع) with their dimensions.
- Real estate deal prices in a target area (Ministry of Justice data).
- Location analysis: urban and demographic data.
- BI dashboards and periodic market reports.
- A platform for brokers to manage and share offers.

Listed data sources: Ministry of Justice, Ministry of Housing, National Address, Ministry of Municipal and Rural Affairs (Balady), Royal Commission for Riyadh City, and brokers and marketing companies.

What we take from Suhail: **the parcel is the unit of the map**, deals sit on real plots inside real plans, and the map stays calm and readable with very little chrome.

Where Nyyf Pro goes further: Suhail is a data platform that brokers look things up in. Nyyf Pro is the broker's **workspace**: the same quality of map, plus instant explainable valuation, the broker's own inventory and clients on the map, matching, and branded sharing. (Suhail's site did not render its content to our fetch, so details above come from a third-party directory and should be checked hands-on. A competitive teardown with screenshots is a task in Phase 0.)

## Experience goals

1. **Calm.** A light, low-contrast basemap with no clutter. Data is the only colour on screen.
2. **One question per zoom level.** City zoom answers "where is expensive?", district zoom answers "what sold here?", parcel zoom answers "what is this plot worth?".
3. **Smooth.** No blocking spinners. Tiles stream in and fade in. Camera moves ease. Selections animate.
4. **Thumb-friendly.** On mobile, everything is one hand: bottom sheet, big targets, search at the top.

## Zoom levels and what appears

| Zoom | Layer shown | Encoding | Tap does |
|---|---|---|---|
| 9 to 11 (city) | Districts (أحياء) | Fill colour = median price per m² (last 12 months), 5-step sequential scale. District names in Arabic. | Fly to district, open district sheet |
| 12 to 14 (district) | Plans (مخططات) outlines + deal clusters + listing clusters | Clusters show count; cluster colour = median price per m² of contents | Expand cluster with an eased zoom |
| 15 to 16 (neighbourhood) | Parcels (where data exists), individual deals and listings | Deal dot colour = price per m²; listing = pin with price label (e.g. "1.2M") | Open deal or listing card |
| 17+ (plot) | Parcels with number, dimensions, street widths | Highlighted outline on selection | Open parcel sheet with valuation |

Rules:
- Labels never overlap; price labels only appear when ≤ 60 are in view.
- Colour scale is fixed per city and metric (not per viewport), so colours mean the same thing everywhere. Legend is a single slim bar.
- Deals (sold, from MOJ) and listings (asking) are visually distinct: deals are small solid dots, listings are pins with a price chip. Broker's own listings use the brand teal.

## Layout

### Mobile
- **Top:** search pill (district, scheme, plot number, street) + filter button.
- **Map:** full screen.
- **Bottom sheet:** three snap points (peek 15%, half 50%, full 92%). Peek shows the one-line answer (e.g. "حي الملقا · 4,850 ر.س/م² · ▲ 6% سنوي").
- **Floating:** layers button (deals, listings, my inventory, watchlist), locate-me, metric switcher.

### Desktop
- Left panel (400 px) replaces the bottom sheet; map fills the rest.
- Hover shows a tooltip; click pins the panel.
- Keyboard: `/` focuses search, `Esc` clears selection, `L` toggles layers.

## Sheets and cards

**District sheet:** median price per m², 12-month sparkline, deal count, YoY change, top 5 schemes by volume, active listings count, asking vs. sold gap, buttons: Watch, Report, Value a plot here.

**Deal card:** date, area, total price, price per m², plan, parcel number if known, and "AI estimate today" with the difference.

**Listing card:** photo, asking price, area, price per m², market estimate with a badge (below market / fair / above market), broker, buttons: Share on WhatsApp, Add to client, Open listing.

**Parcel sheet:** parcel number, plan, dimensions, area, street widths and frontage, last deals on this parcel and around it, instant valuation with range and comparables highlighted on the map.

## Interactions and motion

| Interaction | Behaviour |
|---|---|
| Select district | `flyTo` with ease-out 600 ms, fill highlights with a 150 ms fade, others dim to 40% |
| Expand cluster | Zoom to cluster expansion zoom, 400 ms |
| Open sheet | Spring animation, map padding updates so the selection stays centred above the sheet |
| Filter change | Data updates in place via feature-state or style filters, no reload, 200 ms colour transition |
| Time slider (P1) | Scrubbing animates the district colours month by month |
| Draw area (P1) | Lasso or radius, stats appear in the sheet while drawing |

## Performance budget

- First meaningful paint (districts visible): < 1.5 s on a mid-range phone on 4G.
- Pan and zoom: ≥ 55 fps median, no long tasks over 50 ms during interaction.
- Data delivery: **vector tiles only** (no multi-MB GeoJSON). Districts and plans pre-baked, deals and listings served as dynamic MVT from PostGIS, cached at the CDN.
- JS for the map route under 300 KB gzipped (excluding the map library).

## Visual language

- Basemap: custom light style (and a dark style), muted roads, no POI noise, Arabic labels first.
- Price scale (sequential, colour-blind-safe): teal family from the Nyyf palette for low, through sand, to deep coral for high. Final hex values to be validated in the design phase.
- Typography: an Arabic-first family with good numerals (e.g. IBM Plex Sans Arabic or Tajawal), tabular figures for prices.
- Numbers: short form on the map (1.2M, 850K / ١٫٢ م), full form in sheets. Currency ر.س / SAR.

## Accessibility and localisation
- RTL default, mirrored layout in English.
- All colour encodings also available as numbers in the sheet; legend has text labels.
- Touch targets ≥ 44 px.

## Acceptance criteria (MVP)
1. A new user sees Riyadh districts coloured by price within 1.5 s and understands the legend without help.
2. Tapping any district, deal, or listing opens the correct sheet or card with smooth motion.
3. From a tap on any point, the user gets a valuation with range and comparables in under 3 s.
4. Filters for type, date, price, and area update the map without a page reload.
5. Works in Arabic and English, on mobile and desktop.
