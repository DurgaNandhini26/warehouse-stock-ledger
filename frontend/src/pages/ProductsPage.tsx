import { type FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type { Unit } from "../api/types";
import { Field } from "../components/Field";
import { Empty, ErrorBanner, Loading, Notice } from "../components/Status";
import { formatCost, formatMoney, formatQty } from "../lib/format";
import { useAsync } from "../lib/useAsync";
import { checkQuantity } from "../lib/validation";

const SKU = /^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$/;

export default function ProductsPage() {
  const [search, setSearch] = useState("");
  const products = useAsync(() => api.products({ search: search.trim() || undefined }), [search]);

  return (
    <section>
      <div className="page-head">
        <h1>Products</h1>
      </div>
      <CreateProduct onCreated={products.reload} />
      <div className="filters">
        <label>
          Search SKU or name
          <input value={search} maxLength={100} onChange={(e) => setSearch(e.target.value)} />
        </label>
      </div>
      <ErrorBanner error={products.error} onRetry={products.reload} />
      {products.loading && !products.data && <Loading />}
      {products.data && products.data.items.length === 0 && <Empty>No products found.</Empty>}
      {products.data && products.data.items.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">SKU</th>
                <th scope="col">Name</th>
                <th scope="col">Unit</th>
                <th scope="col" className="num">
                  On hand
                </th>
                <th scope="col" className="num">
                  Reorder level
                </th>
                <th scope="col" className="num">
                  Avg cost
                </th>
                <th scope="col" className="num">
                  Value
                </th>
              </tr>
            </thead>
            <tbody>
              {products.data.items.map((p) => (
                <tr key={p.id} className={p.is_low_stock ? "low" : ""}>
                  <td>
                    <Link to={`/products/${p.id}`}>{p.sku}</Link>
                  </td>
                  <td>{p.name}</td>
                  <td>{p.unit}</td>
                  <td className="num">
                    {formatQty(p.on_hand)} {p.is_low_stock && <span className="badge warn">low</span>}
                  </td>
                  <td className="num">{formatQty(p.reorder_level)}</td>
                  <td className="num">{formatCost(p.avg_cost)}</td>
                  <td className="num">{formatMoney(p.stock_value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function CreateProduct({ onCreated }: { onCreated: () => void }) {
  const [sku, setSku] = useState("");
  const [name, setName] = useState("");
  const [unit, setUnit] = useState<Unit>("kg");
  const [reorder, setReorder] = useState("0");
  const [attempted, setAttempted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [serverError, setServerError] = useState<ApiError | null>(null);
  const [created, setCreated] = useState<string | null>(null);

  const errors: Record<string, string | null> = {
    sku: SKU.test(sku.trim()) ? null : "Letters, digits, . _ - only (max 40), starting with a letter or digit",
    name: name.trim() ? null : "Name is required",
    reorder_level: reorder.trim() === "0" ? null : checkQuantity(reorder, unit)?.replace("Quantity", "Reorder level") ?? null,
  };
  const show = (field: string) =>
    (attempted ? errors[field] : null) ?? (serverError?.field === field ? serverError.message : null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setAttempted(true);
    setServerError(null);
    if (Object.values(errors).some(Boolean)) return;
    setBusy(true);
    try {
      const product = await api.createProduct({ sku: sku.trim(), name: name.trim(), unit, reorder_level: reorder.trim() });
      setCreated(product.sku);
      setSku("");
      setName("");
      setReorder("0");
      setAttempted(false);
      onCreated();
    } catch (err) {
      setServerError(err instanceof ApiError ? err : new ApiError(0, { message: String(err) }));
    } finally {
      setBusy(false);
    }
  }

  return (
    <details className="card">
      <summary>Add a product</summary>
      {created && <Notice kind="success">Created {created}.</Notice>}
      {serverError && !serverError.field && <ErrorBanner error={serverError} />}
      <form className="form compact" onSubmit={submit} noValidate>
        <Field label="SKU" htmlFor="sku" error={show("sku")} hint="Stored in upper case; cannot be changed later">
          <input id="sku" maxLength={40} value={sku} onChange={(e) => setSku(e.target.value)} />
        </Field>
        <Field label="Name" htmlFor="name" error={show("name")}>
          <input id="name" maxLength={200} value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="Unit" htmlFor="unit" hint="Cannot be changed later">
          <select id="unit" value={unit} onChange={(e) => setUnit(e.target.value as Unit)}>
            <option value="kg">kg</option>
            <option value="litre">litre</option>
            <option value="pcs">pcs</option>
          </select>
        </Field>
        <Field label="Reorder level" htmlFor="reorder" error={show("reorder_level")}>
          <input id="reorder" inputMode="decimal" value={reorder} onChange={(e) => setReorder(e.target.value)} />
        </Field>
        <div className="form-actions">
          <button type="submit" className="primary" disabled={busy}>
            {busy ? "Saving…" : "Create product"}
          </button>
        </div>
      </form>
    </details>
  );
}
