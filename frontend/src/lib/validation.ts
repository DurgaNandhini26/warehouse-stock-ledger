// Inline form checks that mirror the backend rules so users see problems before submitting.
// The backend remains the authority: its error (code + field) is always shown if it disagrees.

export function decimalPlaces(value: string): number {
  const frac = value.split(".")[1];
  return frac ? frac.replace(/0+$/, "").length : 0;
}

const NUMBER = /^-?\d+(\.\d+)?$/;

export function checkQuantity(
  raw: string,
  unit: string | undefined,
  opts: { allowNegative?: boolean } = {},
): string | null {
  const value = raw.trim();
  if (value === "") return "Quantity is required";
  if (!NUMBER.test(value)) return "Enter a number like 12 or 12.5";
  const negative = value.startsWith("-");
  if (negative && !opts.allowNegative) return "Quantity must be greater than zero";
  if (/^-?0+(\.0+)?$/.test(value)) return opts.allowNegative ? "Use a non-zero quantity" : "Quantity must be greater than zero";
  if (unit === "pcs" && decimalPlaces(value) > 0) return "Pieces must be whole numbers";
  if (decimalPlaces(value) > 3) return "At most 3 decimal places";
  if (compareMagnitude(value.replace("-", ""), "10000000") > 0) return "Quantity cannot exceed 1,00,00,000";
  return null;
}

export function checkUnitCost(raw: string): string | null {
  const value = raw.trim();
  if (value === "") return "Unit cost is required for IN";
  if (!NUMBER.test(value) || value.startsWith("-")) return "Unit cost must be a positive number";
  if (/^0+(\.0+)?$/.test(value)) return "Unit cost must be greater than zero";
  if (decimalPlaces(value) > 4) return "At most 4 decimal places";
  if (compareMagnitude(value, "10000000") > 0) return "Unit cost cannot exceed ₹1,00,00,000";
  return null;
}

/** Compare two non-negative decimal strings without floats. */
export function compareMagnitude(a: string, b: string): number {
  const [ai = "0", af = ""] = a.split(".");
  const [bi = "0", bf = ""] = b.split(".");
  const width = Math.max(af.length, bf.length);
  const x = BigInt((ai.replace(/^0+/, "") || "0") + af.padEnd(width, "0"));
  const y = BigInt((bi.replace(/^0+/, "") || "0") + bf.padEnd(width, "0"));
  return x === y ? 0 : x > y ? 1 : -1;
}
