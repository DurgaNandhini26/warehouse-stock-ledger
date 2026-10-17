import { Link } from "react-router-dom";
import { api } from "../api/client";
import { ErrorBanner, Loading } from "../components/Status";
import { formatCost, formatIST, formatMoney, formatQty } from "../lib/format";
import { useAsync } from "../lib/useAsync";

export default function ValuationPage() {
  const report = useAsync(() => api.valuation(), []);
  return (
    <section>
      <div className="page-head">
        <h1>Stock valuation</h1>
        <button type="button" onClick={report.reload} disabled={report.loading}>
          Refresh
        </button>
      </div>
      <p className="muted">Quantity on hand × weighted average cost, rounded to paise.</p>
      <ErrorBanner error={report.error} onRetry={report.reload} />
      {report.loading && !report.data && <Loading />}
      {report.data && (
        <>
          <div className="stats">
            <div className="stat">
              <span className="stat-label">Total stock value</span>
              <span className="stat-value">{formatMoney(report.data.total_value)}</span>
            </div>
            <div className="stat">
              <span className="stat-label">As of</span>
              <span className="stat-value small">{formatIST(report.data.as_of)}</span>
            </div>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">SKU</th>
                  <th scope="col">Name</th>
                  <th scope="col" className="num">
                    On hand
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
                {report.data.lines.map((line) => (
                  <tr key={line.product_id}>
                    <td>
                      <Link to={`/products/${line.product_id}`}>{line.sku}</Link>
                    </td>
                    <td>{line.name}</td>
                    <td className="num">{formatQty(line.on_hand, line.unit)}</td>
                    <td className="num">{formatCost(line.avg_cost)}</td>
                    <td className="num strong">{formatMoney(line.value)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <th scope="row" colSpan={4}>
                    Total
                  </th>
                  <td className="num strong">{formatMoney(report.data.total_value)}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
