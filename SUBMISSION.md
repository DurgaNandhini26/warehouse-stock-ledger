# Submission: Problem 3, Warehouse Stock Ledger

## A. What I built

A stock ledger for a small warehouse. Stock is changed only by appending IN, OUT, TRANSFER or
ADJUSTMENT movements, and every balance, average cost and valuation can be recomputed from them.
All Core API features are complete: products, locations, every movement type, reversal, balances
by product/location/both, filtered and paginated history, the low-stock report, the valuation
report and reconcile (read-only check plus repair). All Core UI features are complete: a products ×
bins grid, one entry form per movement type with inline validation, a product ledger with running
balance, plus low-stock, valuation and reconcile pages. From the stretch list only the CSV ledger
export is done. It is live: UI on Vercel (https://warehouse-stock-ledger.vercel.app), API on Render
(https://stock-ledger-api-ec7c.onrender.com/docs), database on Neon Postgres.

## B. Three design decisions

**1. Cached balances behind a per-product row lock**
- **Decision:** `stock_balances` is a cache updated in the same transaction as each movement. That
  transaction first runs `SELECT … FOR UPDATE` on the product row (`BEGIN IMMEDIATE` on SQLite).
- **Alternative considered:** deriving balances with `SUM()` on every read, plus SERIALIZABLE
  isolation and retries.
- **Why I chose this:** the weighted average cost is per product anyway, so serialising per product
  is the natural granularity. Reads stay cheap, and a CHECK `>= 0` backs up the domain check.
- **What it cost me:** a second source of truth that can drift, hence the reconcile endpoint, and a
  replay of average costs to verify the cached average too.

**2. Rules as pure functions; the database as a second guard**
- **Decision:** `plan_movement()` takes a request plus a stock snapshot and returns deltas,
  valuation and the new average, or raises. Only the service layer touches SQL.
- **Alternative considered:** rules in ORM models or DB constraints alone.
- **Why I chose this:** every rule is unit-tested in milliseconds, and reversal reuses all of
  them by being modelled as the inverse movement.
- **What it cost me:** some rules exist twice (domain plus CHECK, trigger or UNIQUE constraint),
  and the DB versions return a generic 409 if they ever fire.

**3. Decimals as scaled integers**
- **Decision:** quantities, costs and values are stored as BIGINT × 10³ / 10⁸ / 10², behind a
  SQLAlchemy type that refuses to round silently.
- **Alternative considered:** `NUMERIC` columns.
- **Why I chose this:** SQLite has no real decimal type (SQLAlchemy would go through floats), and
  this keeps SQLite and Postgres identical and `SUM()` exact.
- **What it cost me:** raw SQL shows integers, and changing a precision means rescaling data.

## C. The hardest part

The weighted average cost. My first version (`9c52617`) rounded the average to 4 decimal places
after every receipt. That looked reasonable, since it is 1/100 of a paisa. The 1,000-receipt test
in `tests/test_domain_valuation.py`, written in M1 (`2d25764`) before the implementation, compared
the cached average with an exact `Fraction` computation and failed: the error was 0.00033, visible
in the 4th decimal. Each rounding is re-weighted into the next average, so the errors accumulate
instead of cancelling. I changed the internal precision to 8 decimals (half-even). Users still
enter costs with at most 4, and money is still rounded to paise. That forced a second change:
reversing an OUT re-enters its stored 8-decimal cost, so reversals now bypass the 4-decimal input
check (`is_reversal`). The fix is in the same commit `9c52617`, and the commit body explains it.
Lesson: precision rules for stored derived values differ from those for user input.

## D. How I handle failure

| Failure | Travels | User sees | Logged |
|---|---|---|---|
| Bad request (bad JSON, wrong type, NaN, unknown enum) | pydantic → `RequestValidationError` handler | 422 `VALIDATION_ERROR`, offending field; the UI marks the field | INFO, field names only |
| Rule violation | `domain` raises `RuleViolation` / `Conflict` → service logs and re-raises → transaction rolls back → handler | 422/409 with a specific code, message, `details` (e.g. available vs requested); the UI shows it next to the field | WARNING with code, product, location ids |
| Database error | constraint → `IntegrityError` → 409 `CONSTRAINT_VIOLATION`; outage → `OperationalError` → 503 | "nothing was saved" / "try again shortly" | WARNING / ERROR with trace |
| Unexpected exception | caught by the request middleware | 500 `INTERNAL_ERROR` + `request_id`, never a trace | ERROR with stack trace and the same `request_id` |

## E. Milestone log

| Milestone | Date completed | Commit |
|---|---|---|
| M0 Scaffold | 2026-10-17 | `0233f78` |
| M1 Domain model | 2026-10-17 | `2d25764` |
| M2 Business rules | 2026-10-17 | `1079c12` |
| M3 API | 2026-10-17 | `aa54309` |
| M4 UI | 2026-10-17 | `9ff9c98` |
| M5 Deployment | 2026-10-20 (live on Render + Vercel + Neon) | `a9f3cd4` |
| M6 Documentation | 2026-10-21 | `3b965c7` (README); final commit tagged `v1.0` |

## F. If I had two more days

1. **Idempotency keys on `POST /movements`.** A retried request after a timeout can double-post
   stock today; this is the most realistic data-quality bug left.
2. **Stock-take mode.** Enter counted quantities and generate `count_correction` adjustments in
   one transaction. It reuses existing rules, so it is cheap and high-value for the "40 vs 36 bags"
   story.
3. **Component tests for the movement form,** the most logic-heavy page.
4. **Running balances stored per movement (or a window-function query),** so the ledger stays fast
   as history grows.
5. **Keep-warm or paid tier for the API.** The free-tier cold start (30–60 s) is the first thing a
   reviewer sees. It is last because it is a hosting decision, not a code change.

## G. Self-assessment

| Criterion | Score | Justification |
|---|---|---|
| Business logic correctness | 5 | All 7 rules enforced in the backend, with boundary tests and concurrency tests (racing OUTs, racing reversals, mid-transfer failure). |
| Code clarity and structure | 4 | Clear api/services/domain/db layering, enforced by ruff. A few long route/presenter functions remain. |
| Error and exception handling | 5 | Distinct error types, one shape, specific codes, no 5xx on 30+ malformed inputs tested, transactions everywhere. |
| Logging and observability | 4 | JSON logs, correlation id in header/body/logs, domain ids, WARNING on violations. No metrics or tracing. |
| Data modelling and persistence | 5 | CHECKs per movement type, UNIQUE reversal link, immutability triggers, indexes, exact decimals, migrations. |
| API design | 4 | Resource paths, correct verbs and status codes, pagination, OpenAPI. Ledger pagination happens after an in-memory computation. |
| UI usability | 4 | Inline validation, loading/error states, actionable messages, responsive CSS. Phone layout only briefly checked. |
| Testing | 4 | 163 backend tests, 98 % coverage (99.5 % domain). Frontend tests cover helpers only. |
| Deployment and operability | 4 | Live on Render/Vercel/Neon from committed config; migrate+seed on start, health check, CI on SQLite and Postgres. It took three fixes to get live (Docker path, a stray word in DATABASE_URL, Vercel Drop), and docker compose was never run locally. |
| Git hygiene | 3 | Milestone-tagged Conventional Commits with "why" bodies, but all made on one day rather than spread over the week. |
| Documentation and write-up | 4 | README follows the required structure, with live links, a rule→code→test map, deploy lessons and honest limitations. |
