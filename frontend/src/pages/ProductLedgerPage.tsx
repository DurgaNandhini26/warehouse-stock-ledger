import { type FormEvent, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { MovementTable } from "../components/MovementTable";
import { Pager } from "../components/Pager";
import { Empty, ErrorBanner, Loading, Notice } from "../components/Status";
import { formatCost, formatMoney, formatQty } from "../lib/format";
import { useAsync } from "../lib/useAsync";
import { checkQuantity } from "../lib/validation";

const PAGE = 100;

export default function ProductLedgerPage() {
  const productId = Number(useParams().productId);
  // ?location=<id> lets other pages (e.g. a click on the stock grid) open the ledger for one bin.
  const [params, setParams] = useSearchParams();
  const rawLocation = params.get("location") ?? "";
  const locationId = /^[1-9]\d{0,9}$/.test(rawLocation) ? rawLocation : "";
  const [offset, setOffset] = useState(0);
  const followLocation = (id: string) => {
    setParams(id ? { location: id } : {}, { replace: true });
    setOffset(0);
  };
  const [version, setVersion] = useState(0);

  const valid = Number.isInteger(productId) && productId > 0;
  const ledger = useAsync(
    () =>
      valid
        ? api.ledger(productId, { location_id: locationId, limit: PAGE, offset })
        : Promise.reject(new ApiError(404, { code: "PRODUCT_NOT_FOUND", message: "Unknown product" })),
    [productId, locationId, offset, version],
  );
  const balances = useAsync(() => (valid ? api.balances({ product_id: productId }) : Promise.resolve(null)), [productId, version]);
  const locations = useAsync(() => api.locations(), []);
  const refresh = () => setVersion((v) => v + 1);

  const running = useMemo(
    () =>
      new Map(
        (ledger.data?.entries ?? []).map((e) => [e.movement.id, { change: e.quantity_change, balance: e.balance_after }]),
      ),
    [ledger.data],
  );
  // Show newest first, like the history page; the running balance is computed oldest-first by the API.
  const movements = useMemo(() => [...(ledger.data?.entries ?? [])].reverse().map((e) => e.movement), [ledger.data]);
  const product = ledger.data?.product;

  return (
    <section>
      <p>
        <Link to="/products">← Products</Link>
      </p>
      <ErrorBanner error={ledger.error} onRetry={ledger.reload} />
      {ledger.loading && !ledger.data && <Loading />}
      {product && (
        <>
          <div className="page-head">
            <h1>
              {product.sku} <span className="sub-inline">{product.name}</span>
            </h1>
            <div className="actions">
              <Link className="button primary" to={`/movements/new?product=${product.id}`}>
                New movement
              </Link>
              <a className="button" href={api.ledgerCsvUrl(product.id, locationId ? Number(locationId) : undefined)}>
                Export CSV
              </a>
            </div>
          </div>
          <div className="stats">
            <Stat label="On hand" value={formatQty(product.on_hand, product.unit)} warn={product.is_low_stock} />
            <Stat label="Reorder level" value={formatQty(product.reorder_level, product.unit)} />
            <Stat label="Average cost" value={formatCost(product.avg_cost)} />
            <Stat label="Stock value" value={formatMoney(product.stock_value)} />
          </div>
          {product.is_low_stock && <Notice kind="warn">At or below its reorder level — this product is on the low-stock report.</Notice>}

          <ReorderEditor productId={product.id} current={product.reorder_level} unit={product.unit} onSaved={refresh} />

          <h2>Balance by bin</h2>
          {balances.data && balances.data.items.length === 0 && <Empty>No stock in any bin.</Empty>}
          {balances.data && balances.data.items.length > 0 && (
            <ul className="chips">
              {balances.data.items.map((b) => (
                <li key={b.location_id}>
                  <Link to={`?location=${b.location_id}`} title={`Show the movements behind ${b.location_code}`}>
                    <strong>{b.location_code}</strong> {formatQty(b.quantity, b.unit)}
                  </Link>
                </li>
              ))}
            </ul>
          )}

          <div className="page-head">
            <h2>Ledger</h2>
            <label className="inline-select">
              Follow
              <select
                value={locationId}
                onChange={(e) => followLocation(e.target.value)}
              >
                <option value="">Whole warehouse</option>
                {locations.data?.items.map((l) => (
                  <option key={l.id} value={l.id}>
                    Bin {l.code}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {ledger.data!.location && (
            <Notice kind="info">
              Bin <strong>{ledger.data!.location.code}</strong> holds{" "}
              <strong>{formatQty(ledger.data!.closing_balance, product.unit)}</strong>. The {ledger.data!.total}{" "}
              movement(s) below add up to exactly that.{" "}
              <button type="button" className="link" onClick={() => followLocation("")}>
                Show whole warehouse
              </button>
            </Notice>
          )}
          <p className="muted small">
            “Balance after” is recomputed from the movements themselves, so it explains the current figure
            ({formatQty(ledger.data!.closing_balance, product.unit)}). Transfers do not change the warehouse total.
          </p>
          {movements.length === 0 ? (
            <Empty>No movements yet.</Empty>
          ) : (
            <>
              <MovementTable movements={movements} running={running} unit={product.unit} onChanged={refresh} />
              <Pager total={ledger.data!.total} limit={PAGE} offset={offset} onChange={setOffset} />
            </>
          )}
        </>
      )}
    </section>
  );
}

function Stat({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className={`stat${warn ? " warn" : ""}`}>
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
    </div>
  );
}

function ReorderEditor({ productId, current, unit, onSaved }: { productId: number; current: string; unit: string; onSaved: () => void }) {
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save(event: FormEvent) {
    event.preventDefault();
    const trimmed = value.trim();
    const problem = trimmed === "0" ? null : checkQuantity(trimmed, unit);
    if (problem) return setError(problem.replace("Quantity", "Reorder level"));
    setBusy(true);
    try {
      await api.updateProduct(productId, { reorder_level: trimmed });
      setValue("");
      setError(null);
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="inline-form" onSubmit={save} noValidate>
      <label htmlFor="reorder">Change reorder level</label>
      <input id="reorder" inputMode="decimal" placeholder={formatQty(current)} value={value} onChange={(e) => setValue(e.target.value)} />
      <button type="submit" disabled={busy || !value.trim()}>
        Save
      </button>
      {error && (
        <span className="field-error" role="alert">
          {error}
        </span>
      )}
    </form>
  );
}
