import type { ReactNode } from "react";
import { ApiError } from "../api/client";

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <p className="muted" role="status">
      {label}
    </p>
  );
}

export function ErrorBanner({ error, onRetry }: { error: ApiError | null; onRetry?: () => void }) {
  if (!error) return null;
  return (
    <div className="banner banner-error" role="alert">
      <strong>{error.message}</strong>
      <div className="banner-meta">
        {error.code !== "UNKNOWN" && <code>{error.code}</code>}
        {error.requestId && <span> · request id {error.requestId}</span>}
        {onRetry && (
          <button type="button" className="link" onClick={onRetry}>
            Retry
          </button>
        )}
      </div>
    </div>
  );
}

export function Notice({ kind, children }: { kind: "success" | "info" | "warn"; children: ReactNode }) {
  return (
    <div className={`banner banner-${kind}`} role="status">
      {children}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="empty">{children}</p>;
}
