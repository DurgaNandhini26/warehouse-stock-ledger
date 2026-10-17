import { Link } from "react-router-dom";
import { api } from "../api/client";
import { Empty, ErrorBanner, Loading } from "../components/Status";
import { formatQty } from "../lib/format";
import { useAsync } from "../lib/useAsync";

export default function LowStockPage() {
  const report = useAsync(() => api.lowStock(), []);
  return (
    <section>
      <div className="page-head">
        <h1>Low stock</h1>
        <button type="button" onClick={report.reload} disabled={report.loading}>
          Refresh
        </button>
      </div>
      <p className="muted">Products whose total across all bins is at or below their reorder level.</p>
      <ErrorBanner error={report.error} onRetry={report.reload} />
      {report.loading && !report.data && <Loading />}
      {report.data && report.data.length === 0 && <Empty>Nothing is at or below its reorder level.</Empty>}
      {report.data && report.data.length > 0 && (
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
                  Reorder level
                </th>
                <th scope="col" className="num">
                  Shortfall
                </th>
                <th scope="col" />
              </tr>
            </thead>
            <tbody>
              {report.data.map(({ product, shortfall }) => (
                <tr key={product.id}>
                  <td>
                    <Link to={`/products/${product.id}`}>{product.sku}</Link>
                  </td>
                  <td>{product.name}</td>
                  <td className="num">{formatQty(product.on_hand, product.unit)}</td>
                  <td className="num">{formatQty(product.reorder_level, product.unit)}</td>
                  <td className="num strong">{formatQty(shortfall, product.unit)}</td>
                  <td>
                    <Link to={`/movements/new?type=IN&product=${product.id}`}>Receive stock</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
