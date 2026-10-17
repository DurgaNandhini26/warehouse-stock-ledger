// Display helpers. Decimal strings are formatted with string/BigInt arithmetic, never floats.

const IST = new Intl.DateTimeFormat("en-IN", {
  timeZone: "Asia/Kolkata",
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

/** Server timestamps are UTC; staff read them in IST. */
export function formatIST(iso: string): string {
  return `${IST.format(new Date(iso))} IST`;
}

/** Round a decimal string half-up to `places` and add Indian digit grouping. */
export function formatDecimal(value: string | null | undefined, places: number): string {
  if (value === null || value === undefined || value === "") return "—";
  const match = /^(-?)(\d+)(?:\.(\d+))?$/.exec(value.trim());
  if (!match) return value;
  const [, sign, intPart = "0", fracPart = ""] = match;
  const scale = 10n ** BigInt(places);
  const digits = BigInt(intPart + fracPart.padEnd(places + 1, "0").slice(0, places + 1));
  const rounded = (digits + 5n) / 10n; // half-up on the extra digit
  const whole = rounded / scale;
  const frac = (rounded % scale).toString().padStart(places, "0");
  const grouped = groupIndian(whole.toString());
  const isZero = rounded === 0n;
  return `${sign && !isZero ? "-" : ""}${grouped}${places > 0 ? `.${frac}` : ""}`;
}

function groupIndian(digits: string): string {
  if (digits.length <= 3) return digits;
  const last3 = digits.slice(-3);
  const rest = digits.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ",");
  return `${rest},${last3}`;
}

export function formatQty(value: string | null | undefined, unit?: string): string {
  if (value === null || value === undefined) return "—";
  const places = unit === "pcs" ? 0 : 3;
  const fixed = formatDecimal(value, places);
  const text = fixed.includes(".") ? fixed.replace(/\.?0+$/, "") : fixed;
  return unit ? `${text} ${unit}` : text;
}

export function formatMoney(value: string | null | undefined): string {
  return value === null || value === undefined ? "—" : `₹${formatDecimal(value, 2)}`;
}

export function formatCost(value: string | null | undefined): string {
  return value === null || value === undefined ? "—" : `₹${formatDecimal(value, 4)}`;
}

export const REASON_LABELS: Record<string, string> = {
  damaged: "Damaged",
  expired: "Expired",
  count_correction: "Count correction",
  theft: "Theft",
  other: "Other (note required)",
};
