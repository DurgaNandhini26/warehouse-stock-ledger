import { useState } from "react";
import { api } from "../api/client";
import type { MovementType } from "../api/types";
import { MovementTable } from "../components/MovementTable";
import { Pager } from "../components/Pager";
import { Empty, ErrorBanner, Loading } from "../components/Status";
import { useAsync } from "../lib/useAsync";

const PAGE = 50;

export default function MovementsPage() {
  const [productId, setProductId] = useState("");
  const [locationId, setLocationId] = useState("");
  const [type, setType] = useState<MovementType | "">("");
  const [reference, setReference] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [offset, setOffset] = useState(0);

  const lookups = useAsync(() => Promise.all([api.products(), api.locations()]), []);
  const query = {
    product_id: productId,
    location_id: locationId,
    type,
    reference: reference.trim(),
    date_from: dateFrom,
    date_to: dateTo,
    limit: PAGE,
    offset,
  };
  const movements = useAsync(() => api.movements(query), [JSON.stringify(query)]);
  const [products, locations] = lookups.data ?? [null, null];

  const resetPage = <T,>(setter: (v: T) => void) => (v: T) => {
    setter(v);
    setOffset(0);
  };

  return (
    <section>
      <div className="page-head">
        <h1>Movement history</h1>
      </div>
      <p className="muted">
        The ledger is append-only: nothing here can be edited or deleted. To fix a mistake, reverse it.
      </p>
      <div className="filters card">
        <label>
          Product
          <select value={productId} onChange={(e) => resetPage(setProductId)(e.target.value)}>
            <option value="">All</option>
            {products?.items.map((p) => (
              <option key={p.id} value={p.id}>
                {p.sku}
              </option>
            ))}
          </select>
        </label>
        <label>
          Bin
          <select value={locationId} onChange={(e) => resetPage(setLocationId)(e.target.value)}>
            <option value="">All</option>
            {locations?.items.map((l) => (
              <option key={l.id} value={l.id}>
                {l.code}
              </option>
            ))}
          </select>
        </label>
        <label>
          Type
          <select value={type} onChange={(e) => resetPage(setType)(e.target.value as MovementType | "")}>
            <option value="">All</option>
            <option>IN</option>
            <option>OUT</option>
            <option>TRANSFER</option>
            <option>ADJUSTMENT</option>
          </select>
        </label>
        <label>
          Reference
          <input value={reference} maxLength={100} onChange={(e) => resetPage(setReference)(e.target.value)} />
        </label>
        <label>
          From (IST)
          <input type="date" value={dateFrom} onChange={(e) => resetPage(setDateFrom)(e.target.value)} />
        </label>
        <label>
          To (IST)
          <input type="date" value={dateTo} onChange={(e) => resetPage(setDateTo)(e.target.value)} />
        </label>
      </div>
      <ErrorBanner error={movements.error ?? lookups.error} onRetry={movements.reload} />
      {movements.loading && !movements.data && <Loading />}
      {movements.data && movements.data.items.length === 0 && <Empty>No movements match these filters.</Empty>}
      {movements.data && movements.data.items.length > 0 && (
        <>
          <MovementTable movements={movements.data.items} onChanged={movements.reload} />
          <Pager total={movements.data.total} limit={PAGE} offset={offset} onChange={setOffset} />
        </>
      )}
    </section>
  );
}
