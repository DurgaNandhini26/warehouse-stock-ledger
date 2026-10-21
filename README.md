# Warehouse Stock Ledger

## 1. Title and one-liner

**Warehouse Stock Ledger**, KJBN Internship **Problem 3: Warehouse Stock Ledger**.
Stock is never edited. Every change is recorded as an immutable movement (IN, OUT, TRANSFER,
ADJUSTMENT), and every balance, average cost and valuation can be recomputed from those movements.

## 2. Live links

| What | URL |
|---|---|
| UI | https://warehouse-stock-ledger.vercel.app |
| API base URL | https://stock-ledger-api-ec7c.onrender.com/api/v1 |
| API docs (Swagger) | https://stock-ledger-api-ec7c.onrender.com/docs |
| Health | https://stock-ledger-api-ec7c.onrender.com/health |
| Repository | https://github.com/DurgaNandhini26/warehouse-stock-ledger |

There is no login, so there are no test credentials. The API runs on Render's free tier, which
sleeps after about 15 minutes idle. **The first request after a sleep can take 30–60 s.** If the
API is still waking up, the UI shows "Cannot reach the API… retry".

## 3. Tech stack

| Layer | Choice |
|---|---|
| Backend | Python 3.13, FastAPI 0.143, SQLAlchemy 2.1, Alembic (migrations), Uvicorn |
| Database | PostgreSQL 16 in production and docker-compose (Neon free tier when hosted); SQLite for zero-setup local runs and the default test run |
| Frontend | TypeScript, React 19, React Router 7, Vite 8; plain CSS, no UI kit |
| Backend hosting | Render (Docker web service, `render.yaml`) |
| Frontend hosting | Vercel (`frontend/vercel.json`) |
| Tests | pytest + pytest-cov (backend), Vitest (frontend helpers) |
| Lint/format | ruff (Python), ESLint + `tsc --noEmit` (TypeScript) |
| CI | GitHub Actions: backend tests on **both** SQLite and Postgres, plus frontend lint/test/build |

All choices are from the recommended list.

## 4. Architecture

```
 Browser (React UI)                         FastAPI app (backend/app)
 ─────────────────                          ─────────────────────────────────────────────────────
 pages/*  ──fetch JSON──►  main.py middleware: request id, timing log, last-resort 500
 lib/validation (inline       │
 hints only)                  ▼
                           api/routes_*.py    shape validation (pydantic), HTTP status, presenters
                              │
                              ▼
                           services/*.py      ONE transaction per use-case: lock product row,
                              │               read snapshot, call domain, write movement + cache
                              ▼
                           domain/*.py        PURE business rules: plan_movement(), reversal_request(),
                              │               weighted_average_cost(), validation. No SQL, no HTTP.
                              ▼
                           db/repositories.py all SQL (parameterised via SQLAlchemy)
                              │
                              ▼
                       PostgreSQL / SQLite: products, locations, movements (append-only,
                       triggers block UPDATE/DELETE), stock_balances (cache, CHECK >= 0)
```

Request flow for `POST /api/v1/movements`: route parses and validates the body → builds a
`MovementRequest` → `services.movements.post_movement` opens a transaction and locks the product
row (`SELECT … FOR UPDATE` on Postgres, `BEGIN IMMEDIATE` on SQLite) → reads cached balances and the
average cost *after* the lock → `domain.movements.plan_movement` returns per-location deltas, the
frozen valuation and the new average cost, or raises a domain error → one `movements` row is
inserted, the balance deltas are applied (`quantity = quantity + d`), the average cost is updated
→ commit. Any exception rolls back everything.

**Folder structure**

| Folder | Purpose |
|---|---|
| `backend/app/domain/` | Business rules as pure functions and the domain error types. Unit-tested without a database. |
| `backend/app/services/` | Use-cases: transactions, locking, orchestration of domain rules and repositories; reports; reconciliation. |
| `backend/app/api/` | HTTP layer: pydantic request/response schemas, routes, error-to-HTTP mapping. |
| `backend/app/db/` | SQLAlchemy models, exact decimal column type, engine/session setup, repositories (all SQL). |
| `backend/migrations/` | Alembic migrations: schema, constraints, indexes, immutability triggers. |
| `backend/tests/` | Domain unit tests, service tests on a real DB (incl. concurrency), API tests, CLI tests. |
| `frontend/src/` | React UI: `api/` (typed client), `pages/`, `components/`, `lib/` (formatting, inline validation). |
| `scripts/` | `migrate_and_seed.sh`, `coverage.sh`. |
| `.github/workflows/` | CI. |

**Where the business rules live, and why there.** In `backend/app/domain/`. Rules there take plain
values (a request plus a snapshot of stock) and return a plan or raise. That makes them testable
in milliseconds with no database, and gives a reviewer one place to read each rule. The service
layer owns the concerns the domain should not know about (locks, transactions, persistence). The
database adds a second line of defence (CHECK constraints, a UNIQUE index on
`reverses_movement_id`, immutability triggers), so a bug in application code still cannot corrupt
the ledger. The UI only repeats some checks to give fast feedback. It is never the authority.

## 5. Running locally

**Prerequisites:** Python 3.12+ (developed on 3.13), Node.js 20+ (developed on 24) with npm, Git.
Docker is optional (only for the compose route).

**Environment variables**

`backend/.env` (copy from `backend/.env.example`):

| Variable | Meaning | Default |
|---|---|---|
| `DATABASE_URL` | SQLAlchemy URL. `sqlite:///./stock_ledger.db` needs no setup; `postgresql://user:pass@host:5432/db` for Postgres (`postgres://` URLs are accepted and normalised) | `sqlite:///./stock_ledger.db` |
| `CORS_ORIGINS` | Comma-separated browser origins allowed to call the API | `http://localhost:5173` |
| `LOG_LEVEL` | `DEBUG` / `INFO` / `WARNING` / `ERROR` | `INFO` |
| `SEED_ON_START` | Container only: seed the DB on start if it has no products | `true` |

`frontend/.env` (copy from `frontend/.env.example`):

| Variable | Meaning | Default |
|---|---|---|
| `VITE_API_BASE_URL` | API origin, no trailing slash (build-time) | `http://localhost:8000` |

**Backend** (from the repo root; on Windows use `.venv\Scripts\python` instead of `.venv/bin/python`):

```bash
cd backend
python -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
cp .env.example .env
.venv/bin/python -m app.cli migrate        # apply migrations
.venv/bin/python -m app.cli seed           # load sample data (skipped if data exists)
.venv/bin/python -m uvicorn app.main:app --port 8000 --reload
```

API: http://localhost:8000/api/v1 · Swagger: http://localhost:8000/docs · Health: http://localhost:8000/health

**UI** (second terminal):

```bash
cd frontend
npm ci
cp .env.example .env
npm run dev
```

UI: http://localhost:5173

**One-command equivalent (Postgres + API + UI):**

```bash
docker compose up --build
```

## 5a. Deployment

The hosted instance uses three free services. Every step below is either a committed file or a
dashboard step listed here.

1. **Database: Neon** (free, does not expire). *Dashboard:* create a project, copy the connection
   string (`postgresql://…?sslmode=require`).
2. **API: Render**, from `render.yaml` (Docker build of `backend/Dockerfile`).
   *Dashboard:* New → Blueprint → select this repo. Render asks for the two `sync: false`
   variables: `DATABASE_URL` = the Neon string, `CORS_ORIGINS` = the Vercel URL from step 3
   (set a placeholder first and update it after step 3).
   On start the container runs `backend/docker-entrypoint.sh`: `python -m app.cli migrate`, then
   `python -m app.cli seed` (only seeds an empty DB), then uvicorn on `$PORT`. No SQL is run by
   hand. Render health-checks `/health`.
3. **UI: Vercel**, from `frontend/vercel.json`. *Dashboard:* Add New → Project → import the GitHub
   repo (not "Vercel Drop", which uploads unbuilt files and serves 404s), set **Root
   Directory = `frontend`**, deploy. The API URL comes from the committed
   `frontend/.env.production`; a `VITE_API_BASE_URL` set in Vercel (type *Config*, not *Secret*,
   because `VITE_` values are public) would override it. Then put the Vercel URL into Render's
   `CORS_ORIGINS` and choose *Save, rebuild and deploy*.

Lessons from the real deploy: paste the Neon string with nothing after it (a stray word ended up
inside `channel_binding=` and the container could not connect), and use Neon's *direct*
(non-pooled) connection string.

**Redeploy after a code change:** push to `main`. Render (`autoDeploy: true`) and Vercel both
rebuild on push. Migrations run automatically on container start.

**Re-seed the hosted database:** from any machine, with the Neon URL:

```bash
cd backend
DATABASE_URL='postgresql://…neon…' .venv/bin/python -m app.cli reset   # drop, migrate, seed
```

`app.cli seed` (or `scripts/migrate_and_seed.sh`) only seeds an empty database. `reset` wipes it
first.

## 6. Running tests and coverage

```bash
cd backend
.venv/bin/python -m pytest                                    # all 163 backend tests (~25 s)
sh ../scripts/coverage.sh                                     # tests + coverage -> backend/coverage.txt, htmlcov/
TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/ledger_test .venv/bin/python -m pytest   # same suite on Postgres
cd ../frontend && npm test                                    # Vitest: formatting + inline validation helpers
```

**Coverage (committed in `backend/coverage.txt`):**

| Scope | Statements | Coverage |
|---|---|---|
| Backend overall (`app/`) | 1392 | **98 %** |
| Business rules: `app/domain/` | 205 | **99.5 %** (1 defensive line) |
| Use-cases: `app/services/` | 325 | **98.5 %** |

**What is covered:** every business rule with boundary tests (quantity 0 / 0.001 / 10,000,000 /
10,000,000.001, pcs whole numbers, cost 0 / −1 / 0.0001 / 5 decimals, stock exactly available vs
+0.001, reorder level "at" vs "just above"). Also: two OUTs racing for the last units, 10 concurrent
OUTs against 5 units, two concurrent reversals of the same movement, a TRANSFER whose destination
write fails midway (rollback verified), reversing an already reversed movement and reversing a
reversal, rounding of the average cost over 1,000 receipts, and reconcile after deliberately
corrupting the cache. Every API error code is exercised, plus 30+ malformed inputs (bad JSON, NaN,
Infinity, 1e400, booleans, ids beyond int32, unknown enum values, extra fields), and every one
asserts a 4xx with the standard error shape. Immutability triggers and CHECK constraints are tested
directly.

**Deliberately not covered:** `config._load_dotenv` reading a real `.env` file and the 503 branch of
`/health` (environment-dependent). The `IntegrityError` fallbacks for lost races on duplicate SKU
or location code are also untested: the pre-check catches duplicates first, and forcing that race
reliably needs DB-level fault injection. The React pages have no component tests; only their
helper functions are unit-tested. The UI was checked manually (section 11).

## 7. API overview

Interactive docs: `/docs` (Swagger) and `/openapi.json`. All paths below are under `/api/v1`
except `/health`. Lists are paginated with `limit` (1–200) and `offset`.

| Method | Path | Purpose | Main error codes |
|---|---|---|---|
| GET | `/health` | Liveness + DB check | 503 |
| GET | `/meta` | Units, movement types, adjustment reasons, limits | – |
| GET | `/products?search=` | List products with on-hand, average cost, value | 422 |
| POST | `/products` | Create product (SKU, name, unit, reorder level) | 409 `DUPLICATE_SKU`, 422 `INVALID_REORDER_LEVEL`/`VALIDATION_ERROR` |
| GET | `/products/{id}` | Product with on-hand and valuation | 404 `PRODUCT_NOT_FOUND` |
| PATCH | `/products/{id}` | Change name / reorder level (SKU and unit are fixed) | 404, 422 |
| GET | `/products/{id}/ledger?location_id=` | Movements oldest-first with running balance (warehouse or one bin) | 404 |
| GET | `/products/{id}/ledger.csv` | Ledger as CSV (stretch) | 404 |
| GET | `/locations` | List bins | 422 |
| POST | `/locations` | Create bin | 409 `DUPLICATE_LOCATION_CODE`, 422 |
| GET / PATCH | `/locations/{id}` | Get / change description | 404 `LOCATION_NOT_FOUND` |
| POST | `/movements` | Post IN / OUT / TRANSFER / ADJUSTMENT (body `type` selects fields) | 409 `INSUFFICIENT_STOCK`; 422 `INVALID_QUANTITY`, `INVALID_UNIT_COST`, `UNIT_COST_NOT_ALLOWED`, `SAME_LOCATION_TRANSFER`, `INVALID_ADJUSTMENT_REASON`, `NOTE_REQUIRED`, `VALIDATION_ERROR`; 404 |
| GET | `/movements?product_id&location_id&type&reference&date_from&date_to` | History, newest first, filters (dates are IST days) | 422 `INVALID_DATE_RANGE` |
| GET | `/movements/{id}` | One movement incl. `is_reversed` / `reversed_by_movement_id` | 404 `MOVEMENT_NOT_FOUND` |
| POST | `/movements/{id}/reversal` | Post the inverse movement | 409 `ALREADY_REVERSED`, `CANNOT_REVERSE_A_REVERSAL`, `INSUFFICIENT_STOCK`; 422 `REASON_REQUIRED`; 404 |
| GET | `/balances?product_id&location_id&include_zero` | Balances by product, by location, or both (+ total when filtered by product) | 404 |
| GET | `/reports/stock-overview` | Products × locations grid | – |
| GET | `/reports/low-stock` | Products at or below reorder level | – |
| GET | `/reports/valuation` | Quantity × average cost per product + total | – |
| GET | `/reconciliation` | Recompute from ledger, report drift (read-only) | – |
| POST | `/reconciliation` | Recompute and overwrite the cache; returns what was fixed | – |

There are deliberately **no** `PUT`, `PATCH` or `DELETE` routes for movements (405).

Example movement bodies:

```json
{"type": "IN", "product_id": 1, "to_location_id": 5, "quantity": "100", "unit_cost": "52.50", "reference": "INV-1", "created_by": "Kavya"}
{"type": "OUT", "product_id": 1, "from_location_id": 1, "quantity": "20", "reference": "SO-9", "created_by": "Meera"}
{"type": "TRANSFER", "product_id": 1, "from_location_id": 5, "to_location_id": 1, "quantity": "80", "created_by": "Arun"}
{"type": "ADJUSTMENT", "product_id": 6, "location_id": 1, "quantity": "-3", "reason_code": "damaged", "created_by": "Ravi"}
```

Decimals may be sent as JSON strings or numbers and are always returned as strings.

## 8. Business rules and assumptions

| # | Rule | Enforced in | Tests |
|---|---|---|---|
| 1 | Movements immutable; mistakes fixed by a reversal that references the original, which stays visible and is marked reversed | No update/delete routes; DB triggers in `migrations/versions/0001_initial_schema.py`; `domain/movements.py:reversal_request`; `services/movements.py:reverse_movement`; UNIQUE `reverses_movement_id`; "reversed" derived in `db/repositories.py:_movement_rows_query` | `test_schema.py::test_movement_rows_cannot_be_updated/deleted`, `::test_a_movement_can_be_reversed_only_once`; `test_domain_movements.py::test_revers*`; `test_services.py::test_reversal_*`, `::test_concurrent_reversals_of_the_same_movement`; `test_api.py::test_reversal_endpoint_and_original_marked`, `::test_movements_have_no_update_or_delete_endpoint` |
| 2 | Balances derived; cache allowed; reconcile recomputes and reports drift | `services/reconciliation.py:reconcile` (balances via `repositories.expected_balances_from_movements`, avg cost via `replay_average_costs`) | `test_services.py::test_reconcile_*`; `test_api.py::test_reconciliation_endpoints`; `test_cli.py::test_corrupt_cache_then_reconcile_*` |
| 3 | Stock never negative, including under concurrency | `domain/movements.py:ensure_stock_available`; product-row lock in `services/movements.py` + `db/repositories.py:lock_product`; `BEGIN IMMEDIATE` in `db/session.py`; CHECK `quantity >= 0` on `stock_balances` | `test_domain_movements.py::test_out_*`; `test_services.py::test_two_outs_racing_for_the_last_units`, `::test_many_concurrent_outs_never_oversell`; `test_schema.py::test_cached_balance_can_never_be_negative` |
| 4 | TRANSFER atomic and a single logical movement | One row with `from` and `to` (CHECK `ck_movements_locations`); single transaction in `services/movements.py:post_movement` / `db/session.py:transaction` | `test_services.py::test_transfer_moves_stock_as_one_movement`, `::test_transfer_where_destination_write_fails_midway_rolls_back` |
| 5 | Weighted average cost; OUT valued at the average at that moment, stored on the movement | `domain/valuation.py:weighted_average_cost`, `movement_value`; `domain/movements.py:plan_movement`; `movements.unit_cost` / `value` columns | `test_domain_valuation.py` (incl. 1,000-receipt rounding test); `test_services.py::test_out_value_is_frozen_when_average_changes_later` |
| 6 | ADJUSTMENT reason from fixed list; "other" needs a note; ± allowed | `domain/enums.py:AdjustmentReason`; `domain/movements.py:adjustment_request`, `_validate_type_specific_fields` | `test_domain_movements.py::test_*adjustment*`, `::test_other_reason_*`; `test_api.py::test_adjustment_other_without_note`, `::test_unknown_adjustment_reason` |
| 7 | Low-stock report: total across locations ≤ reorder level | `services/reports.py:low_stock` | `test_services.py::test_low_stock_includes_products_at_or_below_reorder_level`; `test_api.py::test_reports` |

**Assumptions** (ambiguities I resolved):

1. **Quantity precision:** kg and litre allow up to 3 decimals (1 g / 1 ml); `pcs` must be whole
   numbers. A movement quantity must be > 0 and ≤ 1,00,00,000. Inputs with more decimals than
   allowed are **rejected, not rounded**.
2. **IN cost:** must be > 0. Zero is rejected (free goods are not modelled), as is anything with
   more than 4 decimals or above ₹1,00,00,000 per unit. Only IN accepts `unit_cost`; sending it on
   another type is a 422.
3. **Money:** all amounts are rupees, kept as exact decimals end to end (stored as scaled
   integers, sent as JSON strings). Movement and stock values are rounded **half-even to paise**.
4. **Average cost precision:** stored to **8 decimal places**, rounded half-even. With 4 places the
   average drifted 0.00033 from the exact value after 1,000 receipts. Displayed to 4 places.
5. **Valuation of non-IN movements:** OUT and ADJUSTMENT (either direction) are valued at the
   average cost at that moment. That value is stored on the movement, and the average is unchanged
   by them. A positive adjustment of a product never received is valued at ₹0.
6. **Receiving into empty stock:** when on-hand is 0, the new average is simply the receipt cost.
   When stock runs out, the last average is kept (it values nothing until the next IN).
7. **Reversal = inverse movement:** IN → OUT, OUT → IN, TRANSFER → TRANSFER with locations
   swapped, ADJUSTMENT → ADJUSTMENT in the opposite direction with the same reason code. Same
   quantity; the reference is copied; a reversal reason is required. It goes through the same rules
   as any movement, so reversing a receipt whose stock has already shipped is rejected
   (`INSUFFICIENT_STOCK`).
8. **Reversal valuation:** reversing an OUT returns the units at the cost they left at (the OUT's
   stored cost) and re-averages. Reversing an IN removes the units at the *current* average, like
   any OUT. It does not restore the pre-receipt average, because intervening OUTs already consumed
   blended stock and an exact unwind is impossible.
9. **A reversal cannot itself be reversed** (`CANNOT_REVERSE_A_REVERSAL`). To redo, post a new
   movement. A movement can be reversed at most once (enforced by a UNIQUE index too).
10. **The original is never modified.** "Reversed" and "reversed by #N" are derived from the
    reversal row's `reverses_movement_id`, so the ledger stays strictly append-only.
11. **Low stock is "at or below":** a product with no movements and reorder level 0 has
    0 ≤ 0, so it appears. This is the literal rule.
12. **SKU, bin code and unit are fixed after creation.** Codes are stored upper-case and are
    unique case-insensitively. Products and locations cannot be deleted because immutable history
    references them.
13. **No authentication** (optional per the brief). `created_by` is free text (1–100 chars) that
    the UI remembers per browser.
14. **Time:** stored in UTC, displayed in IST. History date filters (`date_from`, `date_to`) are IST
    calendar days, inclusive. CSV timestamps are UTC ISO-8601.
15. **Reconcile:** `GET` only reports. `POST` locks all products, then overwrites cached balances
    **and** cached average costs with the values replayed from the ledger.
16. **Warehouse-level ledger:** a TRANSFER shows a change of 0 (the total does not move). The
    per-bin ledger shows −/+.
17. **No reviewer clock override:** this problem has no time-based rules, so none is needed.

## 9. Error handling and logging

**Error shape** (every non-2xx response, including 404 for unknown routes and 405):

```json
{"error": {"code": "INSUFFICIENT_STOCK",
           "message": "only 5 available at location 1, cannot remove 5.001",
           "field": null,
           "details": {"location_id": 1, "available": "5", "requested": "5.001"},
           "request_id": "3f9c…"}}
```

| Kind | Raised where | HTTP | Log level |
|---|---|---|---|
| Malformed / wrong type / missing field (`VALIDATION_ERROR`) | pydantic in `api/schemas.py` | 422 | INFO (field names only, never values) |
| Business-rule violation (`INVALID_QUANTITY`, `NOTE_REQUIRED`, …) | `domain/` → `RuleViolation` | 422 | WARNING with code + domain ids |
| Unknown product / location / movement | services → `NotFound` | 404 | WARNING |
| State conflict (`INSUFFICIENT_STOCK`, `ALREADY_REVERSED`, `DUPLICATE_SKU`, …) | domain / services → `Conflict` subclasses | 409 | WARNING with product, location, available, requested |
| DB constraint caught something the domain did not | SQLAlchemy `IntegrityError` | 409 `CONSTRAINT_VIOLATION` | WARNING |
| Database unreachable | SQLAlchemy `OperationalError` | 503 `DATABASE_UNAVAILABLE` | ERROR with trace |
| Anything else | middleware in `main.py` | 500 `INTERNAL_ERROR` (no trace to client) | ERROR with stack trace |

All writes happen inside `db/session.py:transaction`, which rolls back on any exception, so no
failure leaves a partial write.

**Logging:** one JSON object per line on stdout (`app/logging_setup.py`): `ts` (UTC), `level`,
`logger`, `msg`, `request_id`, plus context such as `movement_id`, `product_id`,
`from_location_id`, `to_location_id`, `quantity`, `code`. Every request gets a correlation id:
the incoming `X-Request-ID` header if it is safe (`[A-Za-z0-9._-]{1,64}`), otherwise a generated
UUID. The id is returned in the `X-Request-ID` response header and in every error body. Each
request produces one `request completed` line (method, path, status, duration). Successful
movements log `movement posted` at INFO, rejections log at WARNING, and reconciliation logs drift
at WARNING. Request bodies are not logged. **On the hosted instance:** Render dashboard → the
service → *Logs*.

## 10. Reviewer aids

* **Clock override:** not applicable (no time-based rules; assumption 17).
* **Seed data:** 8 products, 6 bins, 29 movements over the last two weeks: receipts, transfers,
  sales, a damaged and an expired adjustment, and one mistaken OUT (#28) reversed by #29. Four
  products start on the low-stock report. All names and references are invented.
* **Re-seed:** `python -m app.cli reset` (wipe + migrate + seed) or `python -m app.cli seed`
  (only if empty). See 5a for the hosted DB.
* **Corrupt the cache on purpose to test reconcile:**
  `python -m app.cli corrupt-cache --sku RICE-SNM-25 --location A-01 --quantity 40`. Then open the
  UI's *Reconcile* page (or `GET /api/v1/reconciliation`) to see the drift, and press *Repair*
  (`POST /api/v1/reconciliation`). This is a CLI on purpose: there is no debug endpoint on the
  hosted API.
* **Quick edge-case tour in the UI:**
  * *New movement → Dispatch (OUT)*: the form shows bin availability and blocks over-dispatch inline.
    The API also returns 409 `INSUFFICIENT_STOCK` if you bypass the UI.
  * *Receive (IN)* with cost 0: inline error, and 422 `INVALID_UNIT_COST` from the API.
  * *History*: "Reverse…" on any movement. Reversing #28 again shows `ALREADY_REVERSED`.
  * *Products → a product*: running-balance ledger, per-bin view, CSV export.
* **Race test from a shell:** two simultaneous OUTs that each ask for all 178 units of
  TEA-DUST-250 in bin C-01 (seed data). Exactly one gets 201, the other 409
  `INSUFFICIENT_STOCK`. Run it once, or re-seed first.

  ```bash
  API=https://stock-ledger-api-ec7c.onrender.com
  for i in 1 2; do curl -s -o /dev/null -w "%{http_code}\n" -X POST "$API/api/v1/movements" \
    -H 'Content-Type: application/json' \
    -d '{"type":"OUT","product_id":8,"from_location_id":4,"quantity":"178","created_by":"race"}' & done; wait
  ```

## 11. Known limitations

* **Free-tier hosting:** the Render API sleeps after ~15 minutes idle (30–60 s cold start).
  Neon's free tier also suspends compute when idle and resumes on the first query.
* **Docker was never run on the development machine** (no Docker installed). The API image is
  built and run by Render on every deploy. `docker compose up` itself was not tried locally. The
  Postgres code path (row locks, triggers, concurrency tests) runs in the CI Postgres job and
  against the hosted Neon database.
* **SQLite mode serialises all transactions**, reads included (`BEGIN IMMEDIATE`). That is fine
  for local use and tests, but the hosted setup uses Postgres with per-product row locks.
* **Ledger view computes running balances in Python** over all of a product's movements on each
  request, then pages. That is fine for a small warehouse; a large one would need stored running
  balances or a window-function query.
* **The UI loads up to 200 products/locations into dropdowns.** There is no type-ahead search
  beyond that.
* **No idempotency keys.** A client that retries a timed-out POST can double-post. The UI disables
  the submit button while posting, but the API itself does not deduplicate.
* **No authentication or roles.** `created_by` is self-declared.
* **Stretch items:** CSV export of the ledger is done. Stock-take mode and batch/lot tracking with
  expiry are not.
* **Frontend tests cover helper functions only.** Pages were verified by hand in a browser against
  the local API (overview grid, inline validation, posting, ledger, reversal). Phone width is
  handled by CSS (collapsible menu, horizontally scrolling tables) but was checked only briefly.
* Starlette prints a deprecation warning about `httpx` in the test client. It is harmless.

## 12. AI and third-party usage

* **AI assistant:** Claude Code (Anthropic, model Claude Opus 5.5) generated most of this
  repository from the problem statement: data model, business rules, services, API, tests, UI,
  deployment files and these documents. It worked from my prompt and the two assignment PDFs, and
  ran the tests and the app locally to check its own work. Every prompt is logged in
  [`PROMPTS.md`](PROMPTS.md).
* **Libraries:** FastAPI, SQLAlchemy, Alembic, pydantic, Uvicorn, psycopg, pytest, pytest-cov,
  httpx, ruff; React, React Router, Vite, TypeScript, ESLint, Vitest. No templates, scaffolding
  generators or copied project code were used.
