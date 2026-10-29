# 04 · Feature set

Priority: **P0** = MVP (needed for first brokers), **P1** = v1 public launch, **P2** = later.

## A. Market Map (headline, see 05-map-experience-spec.md)
| Feature | Priority |
|---|---|
| District choropleth by median price per m² with a simple legend | P0 |
| Recent deals (MOJ transactions) as dots, clustered, coloured by price per m² | P0 |
| Live listings layer (from broker inventory and imported offers) | P0 |
| Tap a district: bottom sheet with median price, trend sparkline, deal volume, top schemes | P0 |
| Tap a deal or listing: compact card with price, area, price per m², date, AI estimate | P0 |
| Search: district, scheme, street, or coordinates, in Arabic and English | P0 |
| Filters: property type, date range, price range, area range (one slim filter bar) | P0 |
| Metric switcher: price per m², deal volume, YoY change, asking vs. sold gap | P1 |
| Draw an area (lasso or radius) for instant area stats | P1 |
| Time slider to animate prices over months | P1 |
| Plot (parcel) level geometry where data allows | P2 |
| 3D buildings and points of interest (schools, mosques, metro) toggle | P2 |

## B. Instant Valuation (redesigned engine)
| Feature | Priority |
|---|---|
| Value any point or plot: tap on map or search, add area, type, frontage, street width | P0 |
| Output: estimate, range (low to high), confidence, and price per m² | P0 |
| Top 5 to 10 comparable deals shown on map and in a list, with why they match | P0 |
| Valuation history per broker (replaces old ValuationsHistory) | P0 |
| Feedback on each valuation (kept from old app) to improve the model | P1 |
| Adjust comparables manually and recompute | P1 |

## C. Inventory (listings)
| Feature | Priority |
|---|---|
| Add a listing in under 60 seconds: drop a pin, photos, price, area, type, owner | P0 |
| Listing status: draft, active, under offer, sold, withdrawn | P0 |
| Auto price check: flags listings above or below the market estimate | P0 |
| REGA ad licence number and FAL number fields on each listing | P0 |
| Public listing page (shareable link, branded, map embedded) | P1 |
| Bulk import from Excel | P1 |

## D. Clients and Deals (light CRM)
| Feature | Priority |
|---|---|
| Clients: name, phone, type (buyer, seller, investor, tenant), notes | P0 |
| Client requirements (area, budget, type) saved as a map search | P1 |
| Auto-match: new listing or deal fits a client's requirement → notify broker | P1 |
| Deal pipeline (kanban): lead, viewing, negotiation, closed, lost, with commission | P1 |
| One-tap WhatsApp share and call from any client or listing | P0 |

## E. Reports and Sharing
| Feature | Priority |
|---|---|
| Valuation report (PDF and link): estimate, range, comparables map, broker branding | P0 |
| District market report: price trend, volume, top schemes, supply vs. sold | P1 |
| Custom area report from a drawn shape | P1 |
| Report view tracking (client opened the link) | P2 |

## F. Watchlists and Alerts (evolves old Tracklists)
| Feature | Priority |
|---|---|
| Save districts, schemes, areas, or listings to a watchlist | P0 |
| Alerts: new deal in a watched area, price moves more than X%, new under-priced listing | P1 |
| Weekly market digest (email or push) | P2 |

## G. Office and Account
| Feature | Priority |
|---|---|
| Sign in with phone OTP (primary), Google and Apple (secondary) | P0 |
| Broker profile: FAL licence, logo, contact, brand colour (used on reports) | P0 |
| Office workspace: invite agents, roles (owner, manager, agent), shared inventory | P1 |
| Office dashboard: listings, pipeline, valuations, top agents | P1 |
| Subscription plans and billing (Moyasar or Tap) | P1 |

## Dropped or merged from old nyyf
- Standalone "valuate" form page → merged into map tap and search.
- Separate "reports" page with dropdown filters → becomes the map's area stats plus shareable reports.
- "Tracklists" → renamed Watchlists, now area-aware and alert-driven.
- Home dashboard with valuation counts → replaced by the map home plus a "Today" panel (new matches, alerts, follow-ups).
