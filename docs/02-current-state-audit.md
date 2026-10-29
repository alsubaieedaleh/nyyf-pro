# 02 · Current state audit (old nyyf / Muqayyim)

Reviewed from the project's `Real-Estate-App` folder on 2026-10-29.

## What exists

| Area | Stack | Contents |
|---|---|---|
| Web | Angular 17, Angular Material, Tailwind, Mapbox GL 3, Cypress | Landing, auth (email OTP, Google), dashboard, valuate form, map, reports (deal counts and prices), tracklists (watchlists of properties), settings |
| Mobile | Flutter | Early stage: API clients for dashboard, real estate, tracklists; config only |
| Backend | Node/Express + `pg`, Jest tests | Routes: `/api/auth`, `/api/account`, `/api/valuate`, `/api/tracklists`, `/api/dashboard`, `/api/reports` |
| Valuation model | Python Flask + TensorFlow/Keras (`trained_model.h5`, `scaler.pkl`) | 1,010 inputs: area + one-hot district + one-hot scheme (مخطط). Riyadh only. Returns one number |
| Data | Azure Postgres (`postgres` + `ReportMaster` DBs); GeoJSON on S3 | `riyadh_districts.geojson` (129 districts with `average_price_per_meter`), `riyadh_landsOffers.geojson` (~19.9k land offers with price, area, Arabic description), `new_landsOffer.geojson` (~10.9k) |
| Infra | Terraform: AWS Amplify (web), EC2 t2.micro + VPC (backend) | Backend is cloned and started on boot via user data |

## What is worth keeping

- **The domain insight.** District + scheme + area is a real pricing signal, and the MOJ-style deal table (`RealEstates`: Date, Region, City, District, Scheme, Area, PricePerSquareMeter) is the right backbone for market data.
- **The map idea.** District choropleth by price per m², clustered listing points, and the "owner price vs. AI price" popup are exactly the seed of the headline feature. The popup comparison is the most broker-useful idea in the old app.
- **Tracklists.** Watchlists of properties map naturally to broker "portfolios" and client shortlists.
- **Reports.** Deal count and price breakdowns by month, district, and scheme become the market analytics module.
- **Assets.** District polygons, ~30k scraped land offers (useful for training and for the asking-vs-sold gap), Arabic district and scheme vocabularies (`district_schemes.json`).
- **Brand.** The Nyyf name, logos, and teal palette (`#157D79`, `#23BEB9`, `#23E0C0`).

## What must change

### Security (fix before anything is redeployed)

1. **Database password is hard-coded** in `backend/src/database/db.js` (Azure Postgres host and password in source). Rotate it now if the server still exists, and move all secrets to environment or a secrets manager.
2. **SQL injection.** Queries in reports, dashboard, tracklists, and feedback are built by string interpolation of request values. All queries must be parameterised.
3. **JWT secret is random per process start** (`crypto.randomBytes` in `auth.js`), so every restart logs everyone out and multiple instances cannot share sessions.
4. **Mapbox token committed** in `map.component.ts`; Google OAuth client ID is fine to expose but should come from config.
5. **`terraform.tfstate` committed** to the repo, which can hold sensitive values.
6. **CORS config** passes `origin` twice in one object, so only the testing domain is actually allowed.

### Product and architecture

- **Valuation model is too narrow.** One-hot district/scheme with no coordinates, no time, no property type, no street width or frontage, and no uncertainty. It cannot explain itself and cannot extend beyond Riyadh. The `min = 191.38` fallback hides negative predictions instead of fixing them.
- **Map is a single 24 MB GeoJSON download.** Fine for a demo, too slow on mobile. Needs vector tiles and progressive loading.
- **Region and city are hard-coded** to الرياض in the valuation route.
- **Two front ends (Angular + Flutter) with no shared logic** and a mobile app that never got past API stubs.
- **No concept of a broker**: no office, no client, no listing, no deal. The app is built for an individual checking land prices, not for a broker running a business.

## Verdict

Treat Nyyf Pro as a **rebuild that reuses the data, the domain knowledge, and the brand**, not as a refactor of the old code. The old repo stays as reference and as the source of the seed datasets.
