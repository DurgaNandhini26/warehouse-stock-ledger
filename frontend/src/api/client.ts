import type {
  ApiErrorBody,
  Balance,
  Ledger,
  Location,
  LowStockItem,
  Meta,
  Movement,
  Overview,
  Page,
  Product,
  Reconciliation,
  Valuation,
} from "./types";

const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");
export const API_BASE_URL = BASE_URL;

/** Every failed call becomes an ApiError carrying the server's error code and field. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly field: string | null;
  readonly details: Record<string, unknown>;
  readonly requestId: string | null;

  constructor(status: number, body: Partial<ApiErrorBody>) {
    super(body.message ?? "Request failed");
    this.status = status;
    this.code = body.code ?? "UNKNOWN";
    this.field = body.field ?? null;
    this.details = body.details ?? {};
    this.requestId = body.request_id ?? null;
  }
}

type Query = Record<string, string | number | boolean | undefined | null>;

async function request<T>(method: string, path: string, body?: unknown, query?: Query): Promise<T> {
  const url = new URL(BASE_URL + path);
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, String(value));
  }
  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, {
      code: "NETWORK_ERROR",
      message:
        "Cannot reach the API. If it is hosted on a free tier it may be waking up - wait ~30 s and retry.",
    });
  }
  if (!response.ok) {
    let parsed: { error?: Partial<ApiErrorBody> } = {};
    try {
      parsed = await response.json();
    } catch {
      /* non-JSON error page (e.g. proxy); fall through to a generic message */
    }
    throw new ApiError(response.status, parsed.error ?? { message: `HTTP ${response.status}` });
  }
  return (await response.json()) as T;
}

export const api = {
  meta: () => request<Meta>("GET", "/api/v1/meta"),

  products: (query?: { search?: string; limit?: number; offset?: number }) =>
    request<Page<Product>>("GET", "/api/v1/products", undefined, { limit: 200, ...query }),
  product: (id: number) => request<Product>("GET", `/api/v1/products/${id}`),
  createProduct: (body: { sku: string; name: string; unit: string; reorder_level: string }) =>
    request<Product>("POST", "/api/v1/products", body),
  updateProduct: (id: number, body: { name?: string; reorder_level?: string }) =>
    request<Product>("PATCH", `/api/v1/products/${id}`, body),

  locations: () => request<Page<Location>>("GET", "/api/v1/locations", undefined, { limit: 200 }),
  createLocation: (body: { code: string; description: string }) =>
    request<Location>("POST", "/api/v1/locations", body),

  movements: (query: Query) => request<Page<Movement>>("GET", "/api/v1/movements", undefined, query),
  createMovement: (body: Record<string, unknown>) => request<Movement>("POST", "/api/v1/movements", body),
  reverseMovement: (id: number, body: { reason: string; created_by: string }) =>
    request<Movement>("POST", `/api/v1/movements/${id}/reversal`, body),

  balances: (query: Query) =>
    request<{ items: Balance[]; total_quantity: string | null }>("GET", "/api/v1/balances", undefined, query),
  ledger: (productId: number, query: Query) =>
    request<Ledger>("GET", `/api/v1/products/${productId}/ledger`, undefined, query),
  ledgerCsvUrl: (productId: number, locationId?: number) =>
    `${BASE_URL}/api/v1/products/${productId}/ledger.csv${locationId ? `?location_id=${locationId}` : ""}`,

  overview: () => request<Overview>("GET", "/api/v1/reports/stock-overview"),
  lowStock: () => request<LowStockItem[]>("GET", "/api/v1/reports/low-stock"),
  valuation: () => request<Valuation>("GET", "/api/v1/reports/valuation"),
  checkReconciliation: () => request<Reconciliation>("GET", "/api/v1/reconciliation"),
  repairReconciliation: () => request<Reconciliation>("POST", "/api/v1/reconciliation"),
};
