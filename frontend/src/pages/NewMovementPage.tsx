import { type FormEvent, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type { AdjustmentReason, Movement, MovementType } from "../api/types";
import { Field } from "../components/Field";
import { ErrorBanner, Loading, Notice } from "../components/Status";
import { formatMoney, formatQty, REASON_LABELS } from "../lib/format";
import { useOperator } from "../lib/operator";
import { useAsync } from "../lib/useAsync";
import { checkQuantity, checkUnitCost, compareMagnitude } from "../lib/validation";

const TYPES: { type: MovementType; label: string; help: string }[] = [
  { type: "IN", label: "Receive (IN)", help: "Goods arriving from a supplier. Updates the average cost." },
  { type: "OUT", label: "Dispatch (OUT)", help: "Goods leaving for a customer, valued at the current average cost." },
  { type: "TRANSFER", label: "Transfer", help: "Move stock between two bins. Recorded as one movement." },
  { type: "ADJUSTMENT", label: "Adjustment", help: "Correct stock for damage, expiry, theft or a count difference." },
];

type Errors = Partial<Record<string, string>>;

export default function NewMovementPage() {
  const [params, setParams] = useSearchParams();
  const type = (TYPES.find((t) => t.type === params.get("type"))?.type ?? "IN") as MovementType;
  const [operator, setOperator] = useOperator();

  const [productId, setProductId] = useState(params.get("product") ?? "");
  const [fromId, setFromId] = useState("");
  const [toId, setToId] = useState("");
  const [quantity, setQuantity] = useState("");
  const [direction, setDirection] = useState<"add" | "remove">("remove");
  const [unitCost, setUnitCost] = useState("");
  const [reasonCode, setReasonCode] = useState<AdjustmentReason | "">("");
  const [note, setNote] = useState("");
  const [reference, setReference] = useState("");
  const [attempted, setAttempted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [serverError, setServerError] = useState<ApiError | null>(null);
  const [posted, setPosted] = useState<Movement | null>(null);

  const lookups = useAsync(() => Promise.all([api.products(), api.locations(), api.meta()]), []);
  const balances = useAsync(
    () => (productId ? api.balances({ product_id: productId }) : Promise.resolve(null)),
    [productId, posted?.id],
  );
  const [products, locations, meta] = lookups.data ?? [null, null, null];
  const product = products?.items.find((p) => String(p.id) === productId);
  const adjustmentLocation = direction === "add" ? toId : fromId;
  const sourceId = type === "ADJUSTMENT" ? (direction === "remove" ? fromId : "") : fromId;
  const available = useMemo(() => {
    if (!sourceId || !balances.data) return null;
    return balances.data.items.find((b) => String(b.location_id) === sourceId)?.quantity ?? "0";
  }, [sourceId, balances.data]);

  const needsFrom = type === "OUT" || type === "TRANSFER";
  const needsTo = type === "IN" || type === "TRANSFER";

  const errors: Errors = {};
  if (!productId) errors.product_id = "Choose a product";
  if (needsFrom && !fromId) errors.from_location_id = "Choose the source bin";
  if (needsTo && !toId) errors.to_location_id = "Choose the destination bin";
  if (type === "TRANSFER" && fromId && fromId === toId) errors.to_location_id = "Must differ from the source bin";
  if (type === "ADJUSTMENT" && !adjustmentLocation) errors.location_id = "Choose the bin";
  const qtyError = checkQuantity(quantity, product?.unit);
  if (qtyError) errors.quantity = qtyError;
  else if (available !== null && compareMagnitude(quantity.trim(), available) > 0)
    errors.quantity = `Only ${formatQty(available, product?.unit)} available in this bin`;
  if (type === "IN") {
    const costError = checkUnitCost(unitCost);
    if (costError) errors.unit_cost = costError;
  }
  if (type === "ADJUSTMENT" && !reasonCode) errors.reason_code = "Choose a reason";
  if (type === "ADJUSTMENT" && reasonCode === meta?.reason_requiring_note && !note.trim())
    errors.reason = "A note is required when the reason is 'other'";
  if (!operator.trim()) errors.created_by = "Enter your name so the movement is attributable";

  // Server-side errors win: show them next to the field the API named.
  const serverField = serverError?.field === "location_id" ? "location_id" : serverError?.field;
  const fieldError = (name: string) =>
    (attempted ? errors[name] : undefined) ?? (serverField === name ? serverError?.message : undefined);
  const insufficient = serverError?.code === "INSUFFICIENT_STOCK" ? serverError.message : undefined;

  function switchType(next: MovementType) {
    setParams((prev) => {
      const copy = new URLSearchParams(prev);
      copy.set("type", next);
      return copy;
    });
    setServerError(null);
    setAttempted(false);
    setPosted(null);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setAttempted(true);
    setServerError(null);
    if (Object.keys(errors).length > 0) return;
    const base = {
      type,
      product_id: Number(productId),
      created_by: operator.trim(),
      reference: reference.trim() || undefined,
      reason: note.trim() || undefined,
    };
    let body: Record<string, unknown>;
    if (type === "IN") body = { ...base, to_location_id: Number(toId), quantity: quantity.trim(), unit_cost: unitCost.trim() };
    else if (type === "OUT") body = { ...base, from_location_id: Number(fromId), quantity: quantity.trim() };
    else if (type === "TRANSFER")
      body = { ...base, from_location_id: Number(fromId), to_location_id: Number(toId), quantity: quantity.trim() };
    else
      body = {
        ...base,
        location_id: Number(adjustmentLocation),
        quantity: `${direction === "remove" ? "-" : ""}${quantity.trim()}`,
        reason_code: reasonCode,
      };
    setSubmitting(true);
    try {
      const movement = await api.createMovement(body);
      setPosted(movement);
      setQuantity("");
      setUnitCost("");
      setNote("");
      setReference("");
      setAttempted(false);
    } catch (err) {
      setServerError(err instanceof ApiError ? err : new ApiError(0, { message: String(err) }));
    } finally {
      setSubmitting(false);
    }
  }

  const locationOptions = locations?.items.map((loc) => (
    <option key={loc.id} value={loc.id}>
      {loc.code} — {loc.description}
    </option>
  ));
  const blockingErrors = attempted && Object.keys(errors).length > 0;

  return (
    <section>
      <div className="page-head">
        <h1>New movement</h1>
      </div>
      <div className="tabs" role="tablist" aria-label="Movement type">
        {TYPES.map((t) => (
          <button
            key={t.type}
            type="button"
            role="tab"
            aria-selected={t.type === type}
            className={t.type === type ? "tab active" : "tab"}
            onClick={() => switchType(t.type)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <p className="muted">{TYPES.find((t) => t.type === type)?.help}</p>

      <ErrorBanner error={lookups.error} onRetry={lookups.reload} />
      {lookups.loading && <Loading />}
      {posted && (
        <Notice kind="success">
          Posted movement #{posted.id}: {posted.type} {formatQty(posted.quantity, product?.unit)} of {posted.sku}
          {posted.value && <> valued at {formatMoney(posted.value)}</>}.{" "}
          <Link to={`/products/${posted.product_id}`}>View ledger</Link>
        </Notice>
      )}
      {serverError && !serverField && !insufficient && <ErrorBanner error={serverError} />}

      {products && locations && (
        <form className="card form" onSubmit={submit} noValidate>
          <Field label="Product" htmlFor="product" error={fieldError("product_id")}>
            <select id="product" value={productId} onChange={(e) => setProductId(e.target.value)}>
              <option value="">Select a product…</option>
              {products.items.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.sku} — {p.name} ({p.unit})
                </option>
              ))}
            </select>
          </Field>

          {type === "ADJUSTMENT" && (
            <fieldset className="field">
              <legend>Direction</legend>
              <label className="inline">
                <input type="radio" checked={direction === "remove"} onChange={() => setDirection("remove")} /> Remove
                stock (−)
              </label>
              <label className="inline">
                <input type="radio" checked={direction === "add"} onChange={() => setDirection("add")} /> Add stock (+)
              </label>
            </fieldset>
          )}

          {(needsFrom || (type === "ADJUSTMENT" && direction === "remove")) && (
            <Field
              label={type === "ADJUSTMENT" ? "Bin" : "From bin"}
              htmlFor="from"
              error={fieldError(type === "ADJUSTMENT" ? "location_id" : "from_location_id")}
              hint={available !== null ? `Available: ${formatQty(available, product?.unit)}` : undefined}
            >
              <select id="from" value={fromId} onChange={(e) => setFromId(e.target.value)}>
                <option value="">Select a bin…</option>
                {locationOptions}
              </select>
            </Field>
          )}
          {(needsTo || (type === "ADJUSTMENT" && direction === "add")) && (
            <Field
              label={type === "ADJUSTMENT" ? "Bin" : "To bin"}
              htmlFor="to"
              error={fieldError(type === "ADJUSTMENT" ? "location_id" : "to_location_id")}
            >
              <select id="to" value={toId} onChange={(e) => setToId(e.target.value)}>
                <option value="">Select a bin…</option>
                {locationOptions}
              </select>
            </Field>
          )}

          <Field
            label={`Quantity${product ? ` (${product.unit})` : ""}`}
            htmlFor="quantity"
            error={fieldError("quantity") ?? insufficient}
            hint={product?.unit === "pcs" ? "Whole numbers only" : "Up to 3 decimal places"}
          >
            <input
              id="quantity"
              inputMode="decimal"
              autoComplete="off"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              placeholder="e.g. 25"
            />
          </Field>

          {type === "IN" && (
            <Field label="Unit cost (₹ per unit)" htmlFor="cost" error={fieldError("unit_cost")} hint="Must be greater than 0, up to 4 decimals">
              <input id="cost" inputMode="decimal" autoComplete="off" value={unitCost} onChange={(e) => setUnitCost(e.target.value)} placeholder="e.g. 52.50" />
            </Field>
          )}

          {type === "ADJUSTMENT" && meta && (
            <Field label="Reason" htmlFor="reason-code" error={fieldError("reason_code")}>
              <select id="reason-code" value={reasonCode} onChange={(e) => setReasonCode(e.target.value as AdjustmentReason)}>
                <option value="">Select a reason…</option>
                {meta.adjustment_reasons.map((r) => (
                  <option key={r} value={r}>
                    {REASON_LABELS[r] ?? r}
                  </option>
                ))}
              </select>
            </Field>
          )}

          <Field
            label={type === "ADJUSTMENT" && reasonCode === "other" ? "Note (required)" : "Note (optional)"}
            htmlFor="note"
            error={fieldError("reason")}
          >
            <input id="note" maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} />
          </Field>
          <Field label="Reference (invoice / order no.)" htmlFor="reference" error={fieldError("reference")}>
            <input id="reference" maxLength={100} value={reference} onChange={(e) => setReference(e.target.value)} placeholder="e.g. INV-1042" />
          </Field>
          <Field label="Your name" htmlFor="operator" error={fieldError("created_by")} hint="Saved in this browser">
            <input id="operator" maxLength={100} value={operator} onChange={(e) => setOperator(e.target.value)} />
          </Field>

          <div className="form-actions">
            <button type="submit" className="primary" disabled={submitting || blockingErrors}>
              {submitting ? "Posting…" : `Post ${type}`}
            </button>
            {blockingErrors && <span className="field-error">Fix the highlighted fields first.</span>}
          </div>
        </form>
      )}
    </section>
  );
}
