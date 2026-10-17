export function Pager({
  total,
  limit,
  offset,
  onChange,
}: {
  total: number;
  limit: number;
  offset: number;
  onChange: (offset: number) => void;
}) {
  if (total <= limit) return <p className="muted small">{total} record(s)</p>;
  const from = offset + 1;
  const to = Math.min(offset + limit, total);
  return (
    <div className="pager">
      <button type="button" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>
        ← Previous
      </button>
      <span>
        {from}–{to} of {total}
      </span>
      <button type="button" disabled={to >= total} onClick={() => onChange(offset + limit)}>
        Next →
      </button>
    </div>
  );
}
