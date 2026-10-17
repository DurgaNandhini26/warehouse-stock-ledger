import { type FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type { Movement } from "../api/types";
import { formatCost, formatIST, formatMoney, formatQty, REASON_LABELS } from "../lib/format";
import { useOperator } from "../lib/operator";

interface Props {
  movements: Movement[];
  /** Extra columns for the ledger view: change and running balance, keyed by movement id. */
  running?: Map<number, { change: string; balance: string }>;
  unit?: string;
  onChanged: () => void;
}

export function MovementTable({ movements, running, unit, onChanged }: Props) {
  const [reversing, setReversing] = useState<number | null>(null);

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th scope="col">#</th>
            <th scope="col">When (IST)</th>
            <th scope="col">Type</th>
            {!running && <th scope="col">Product</th>}
            <th scope="col">From → To</th>
            <th scope="col" className="num">
              Qty
            </th>
            {running && (
              <>
                <th scope="col" className="num">
                  Change
                </th>
                <th scope="col" className="num">
                  Balance after
                </th>
              </>
            )}
            <th scope="col" className="num">
              Unit cost
            </th>
            <th scope="col" className="num">
              Value
            </th>
            <th scope="col">Reason / reference</th>
            <th scope="col">By</th>
            <th scope="col">Status</th>
          </tr>
        </thead>
        <tbody>
          {movements.map((m) => {
            const run = running?.get(m.id);
            return (
              <tr key={m.id} className={m.is_reversed ? "reversed" : ""}>
                <td>{m.id}</td>
                <td className="nowrap">{formatIST(m.created_at)}</td>
                <td>
                  <span className={`badge type-${m.type.toLowerCase()}`}>{m.type}</span>
                </td>
                {!running && (
                  <td>
                    <Link to={`/products/${m.product_id}`}>{m.sku}</Link>
                  </td>
                )}
                <td className="nowrap">
                  {m.from_location_code ?? "—"} → {m.to_location_code ?? "—"}
                </td>
                <td className="num">{formatQty(m.quantity, unit)}</td>
                {run && (
                  <>
                    <td className={`num ${run.change.startsWith("-") ? "neg" : ""}`}>
                      {run.change.startsWith("-") || /^0(\.0+)?$/.test(run.change) ? "" : "+"}
                      {formatQty(run.change)}
                    </td>
                    <td className="num strong">{formatQty(run.balance)}</td>
                  </>
                )}
                <td className="num">{formatCost(m.unit_cost)}</td>
                <td className="num">{formatMoney(m.value)}</td>
                <td>
                  {m.reason_code && <span className="badge">{REASON_LABELS[m.reason_code] ?? m.reason_code}</span>}{" "}
                  {m.reason}
                  {m.reference && <span className="sub">{m.reference}</span>}
                </td>
                <td>{m.created_by}</td>
                <td className="nowrap">
                  {m.reverses_movement_id && <span className="badge info">reverses #{m.reverses_movement_id}</span>}
                  {m.is_reversed && <span className="badge muted">reversed by #{m.reversed_by_movement_id}</span>}
                  {!m.is_reversed && !m.reverses_movement_id && (
                    <button type="button" className="small" onClick={() => setReversing(m.id)}>
                      Reverse…
                    </button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {reversing !== null && (
        <ReverseDialog
          movement={movements.find((m) => m.id === reversing)!}
          onClose={() => setReversing(null)}
          onDone={() => {
            setReversing(null);
            onChanged();
          }}
        />
      )}
    </div>
  );
}

function ReverseDialog({ movement, onClose, onDone }: { movement: Movement; onClose: () => void; onDone: () => void }) {
  const [operator, setOperator] = useOperator();
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!reason.trim()) return setError("Explain why this movement is being reversed.");
    if (!operator.trim()) return setError("Enter your name.");
    setBusy(true);
    setError(null);
    try {
      await api.reverseMovement(movement.id, { reason: reason.trim(), created_by: operator.trim() });
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? `${err.message} (${err.code})` : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="dialog-backdrop" role="presentation" onClick={onClose}>
      <form
        className="dialog card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="reverse-title"
        onClick={(e) => e.stopPropagation()}
        onSubmit={submit}
      >
        <h2 id="reverse-title">Reverse movement #{movement.id}</h2>
        <p className="muted">
          This posts the exact opposite movement ({movement.type} {movement.quantity} of {movement.sku}). The original
          stays in the history, marked as reversed. A reversal cannot itself be reversed.
        </p>
        <label htmlFor="rev-reason">Reason</label>
        <input id="rev-reason" autoFocus maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />
        <label htmlFor="rev-operator">Your name</label>
        <input id="rev-operator" maxLength={100} value={operator} onChange={(e) => setOperator(e.target.value)} />
        {error && (
          <p className="field-error" role="alert">
            {error}
          </p>
        )}
        <div className="form-actions">
          <button type="button" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="danger" disabled={busy}>
            {busy ? "Reversing…" : "Post reversal"}
          </button>
        </div>
      </form>
    </div>
  );
}
