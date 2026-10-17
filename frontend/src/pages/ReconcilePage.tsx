import { useState } from "react";
import { ApiError, api } from "../api/client";
import type { Reconciliation } from "../api/types";
import { ErrorBanner, Loading, Notice } from "../components/Status";
import { formatCost, formatIST, formatQty } from "../lib/format";
import { useAsync } from "../lib/useAsync";

export default function ReconcilePage() {
  const check = useAsync(() => api.checkReconciliation(), []);
  const [repairResult, setRepairResult] = useState<Reconciliation | null>(null);
  const [repairError, setRepairError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);

  async function repair() {
    if (!window.confirm("Overwrite the cached balances with the values recomputed from the ledger?")) return;
    setBusy(true);
    setRepairError(null);
    try {
      setRepairResult(await api.repairReconciliation());
      check.reload();
    } catch (err) {
      setRepairError(err instanceof ApiError ? err : new ApiError(0, { message: String(err) }));
    } finally {
      setBusy(false);
    }
  }

  const report = check.data;
  return (
    <section>
      <div className="page-head">
        <h1>Reconcile</h1>
        <button type="button" onClick={check.reload} disabled={check.loading}>
          Re-check
        </button>
      </div>
      <p className="muted">
        Balances shown elsewhere come from a cache for speed. This page recomputes every balance and average cost from
        the movements alone and compares.
      </p>
      <ErrorBanner error={check.error ?? repairError} onRetry={check.reload} />
      {check.loading && !report && <Loading label="Recomputing from the ledger…" />}
      {repairResult && (
        <Notice kind="success">
          Repair done: fixed {repairResult.balance_drift.length} balance(s) and {repairResult.average_cost_drift.length}{" "}
          average cost(s).
        </Notice>
      )}
      {report && (
        <>
          {report.consistent ? (
            <Notice kind="success">
              Consistent — {report.balances_checked} balances and {report.products_checked} products match the ledger
              (checked {formatIST(report.checked_at)}).
            </Notice>
          ) : (
            <Notice kind="warn">
              Drift found: {report.balance_drift.length} balance(s), {report.average_cost_drift.length} average cost(s)
              differ from the ledger.{" "}
              <button type="button" className="danger" onClick={repair} disabled={busy}>
                {busy ? "Repairing…" : "Repair cache from ledger"}
              </button>
            </Notice>
          )}
          {report.balance_drift.length > 0 && (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col">SKU</th>
                    <th scope="col">Bin</th>
                    <th scope="col" className="num">
                      Cache says
                    </th>
                    <th scope="col" className="num">
                      Ledger says
                    </th>
                    <th scope="col" className="num">
                      Difference
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {report.balance_drift.map((d) => (
                    <tr key={`${d.product_id}-${d.location_id}`}>
                      <td>{d.sku}</td>
                      <td>{d.location_code}</td>
                      <td className="num">{formatQty(d.cached)}</td>
                      <td className="num">{formatQty(d.expected)}</td>
                      <td className="num strong">{formatQty(d.difference)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {report.average_cost_drift.length > 0 && (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col">SKU</th>
                    <th scope="col" className="num">
                      Cached avg cost
                    </th>
                    <th scope="col" className="num">
                      Replayed avg cost
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {report.average_cost_drift.map((d) => (
                    <tr key={d.product_id}>
                      <td>{d.sku}</td>
                      <td className="num">{formatCost(d.cached)}</td>
                      <td className="num">{formatCost(d.expected)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}
