import { Link } from "react-router-dom";
import { api } from "../api/client";
import { Empty, ErrorBanner, Loading } from "../components/Status";
import { formatQty } from "../lib/format";
import { useAsync } from "../lib/useAsync";

export default function OverviewPage() {
  const { data, error, loading, reload } = useAsync(() => api.overview(), []);

  return (
    <section>
      <div className="page-head">
        <h1>Stock overview</h1>
        <div className="actions">
          <button type="button" onClick={reload} disabled={loading}>
            Refresh
          </button>
          <Link className="button primary" to="/movements/new">
            New movement
          </Link>
        </div>
      </div>
      <p className="muted">
        Current balance of every product in every bin. Every number here is the sum of recorded movements —
        open a product to see the movements behind it.
      </p>
      <ErrorBanner error={error} onRetry={reload} />
      {loading && !data && <Loading />}
      {data && data.rows.length === 0 && <Empty>No products yet. Add one on the Products page.</Empty>}
      {data && data.rows.length > 0 && (
        <div className="table-wrap">
          <table className="grid">
            <thead>
              <tr>
                <th scope="col" className="sticky">
                  Product
                </th>
                {data.locations.map((loc) => (
                  <th key={loc.id} scope="col" className="num" title={loc.description}>
                    {loc.code}
                  </th>
                ))}
                <th scope="col" className="num">
                  Total
                </th>
                <th scope="col" className="num">
                  Reorder at
                </th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row) => (
                <tr key={row.product_id} className={row.is_low_stock ? "low" : ""}>
                  <th scope="row" className="sticky">
                    <Link to={`/products/${row.product_id}`}>{row.sku}</Link>
                    <span className="sub">{row.name}</span>
                  </th>
                  {data.locations.map((loc) => {
                    const qty = row.quantities[String(loc.id)];
                    return (
                      <td key={loc.id} className="num">
                        {qty ? formatQty(qty) : <span className="faint">·</span>}
                      </td>
                    );
                  })}
                  <td className="num strong">
                    {formatQty(row.total, row.unit)}
                    {row.is_low_stock && <span className="badge warn">low</span>}
                  </td>
                  <td className="num">{formatQty(row.reorder_level, row.unit)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
