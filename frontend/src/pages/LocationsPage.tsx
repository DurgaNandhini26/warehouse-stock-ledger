import { type FormEvent, useState } from "react";
import { ApiError, api } from "../api/client";
import { Field } from "../components/Field";
import { Empty, ErrorBanner, Loading } from "../components/Status";
import { formatIST } from "../lib/format";
import { useAsync } from "../lib/useAsync";

const CODE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,29}$/;

export default function LocationsPage() {
  const locations = useAsync(() => api.locations(), []);
  const [code, setCode] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!CODE.test(code.trim())) return setError("Letters, digits, . _ - only (max 30)");
    setBusy(true);
    setError(null);
    try {
      await api.createLocation({ code: code.trim(), description: description.trim() });
      setCode("");
      setDescription("");
      locations.reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <div className="page-head">
        <h1>Locations (bins)</h1>
      </div>
      <form className="card form compact" onSubmit={submit} noValidate>
        <Field label="Bin code" htmlFor="code" error={error}>
          <input id="code" maxLength={30} value={code} onChange={(e) => setCode(e.target.value)} placeholder="e.g. A-03" />
        </Field>
        <Field label="Description" htmlFor="desc">
          <input id="desc" maxLength={200} value={description} onChange={(e) => setDescription(e.target.value)} />
        </Field>
        <div className="form-actions">
          <button type="submit" className="primary" disabled={busy}>
            Add bin
          </button>
        </div>
      </form>
      <ErrorBanner error={locations.error} onRetry={locations.reload} />
      {locations.loading && !locations.data && <Loading />}
      {locations.data && locations.data.items.length === 0 && <Empty>No bins yet.</Empty>}
      {locations.data && locations.data.items.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">Code</th>
                <th scope="col">Description</th>
                <th scope="col">Created (IST)</th>
              </tr>
            </thead>
            <tbody>
              {locations.data.items.map((l) => (
                <tr key={l.id}>
                  <td className="strong">{l.code}</td>
                  <td>{l.description}</td>
                  <td>{formatIST(l.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
