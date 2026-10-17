// Shapes returned by the API. Decimals arrive as strings and stay strings in the UI.

export type Unit = "kg" | "pcs" | "litre";
export type MovementType = "IN" | "OUT" | "TRANSFER" | "ADJUSTMENT";
export type AdjustmentReason = "damaged" | "expired" | "count_correction" | "theft" | "other";

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface Product {
  id: number;
  sku: string;
  name: string;
  unit: Unit;
  reorder_level: string;
  avg_cost: string;
  on_hand: string;
  stock_value: string;
  is_low_stock: boolean;
  created_at: string;
}

export interface Location {
  id: number;
  code: string;
  description: string;
  created_at: string;
}

export interface Movement {
  id: number;
  type: MovementType;
  product_id: number;
  sku: string;
  from_location_id: number | null;
  from_location_code: string | null;
  to_location_id: number | null;
  to_location_code: string | null;
  quantity: string;
  unit_cost: string | null;
  value: string | null;
  reason_code: AdjustmentReason | null;
  reason: string | null;
  reference: string | null;
  created_at: string;
  created_by: string;
  reverses_movement_id: number | null;
  reversed_by_movement_id: number | null;
  is_reversed: boolean;
}

export interface LedgerEntry {
  movement: Movement;
  quantity_change: string;
  balance_after: string;
}

export interface Ledger {
  product: Product;
  location: Location | null;
  entries: LedgerEntry[];
  total: number;
  limit: number;
  offset: number;
  closing_balance: string;
}

export interface Balance {
  product_id: number;
  sku: string;
  product_name: string;
  unit: Unit;
  location_id: number;
  location_code: string;
  quantity: string;
}

export interface Overview {
  locations: Location[];
  rows: {
    product_id: number;
    sku: string;
    name: string;
    unit: Unit;
    reorder_level: string;
    is_low_stock: boolean;
    quantities: Record<string, string>;
    total: string;
  }[];
}

export interface LowStockItem {
  product: Product;
  shortfall: string;
}

export interface Valuation {
  lines: {
    product_id: number;
    sku: string;
    name: string;
    unit: Unit;
    on_hand: string;
    avg_cost: string;
    value: string;
  }[];
  total_value: string;
  as_of: string;
}

export interface Reconciliation {
  consistent: boolean;
  repaired: boolean;
  checked_at: string;
  balances_checked: number;
  products_checked: number;
  balance_drift: {
    product_id: number;
    sku: string;
    location_id: number;
    location_code: string;
    cached: string;
    expected: string;
    difference: string;
  }[];
  average_cost_drift: { product_id: number; sku: string; cached: string; expected: string }[];
}

export interface Meta {
  units: Unit[];
  movement_types: MovementType[];
  adjustment_reasons: AdjustmentReason[];
  reason_requiring_note: AdjustmentReason;
  quantity_decimals: number;
  unit_cost_decimals: number;
  max_quantity: string;
  max_unit_cost: string;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  field: string | null;
  details: Record<string, unknown>;
  request_id: string;
}
