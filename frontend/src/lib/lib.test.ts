import { describe, expect, it } from "vitest";
import { formatDecimal, formatIST, formatQty } from "./format";
import { checkQuantity, checkUnitCost, compareMagnitude } from "./validation";

describe("formatDecimal", () => {
  it("rounds half-up without floats and groups Indian style", () => {
    expect(formatDecimal("1234567.005", 2)).toBe("12,34,567.01");
    expect(formatDecimal("0.1", 2)).toBe("0.10");
    expect(formatDecimal("55.00000000", 4)).toBe("55.0000");
    expect(formatDecimal("-0.001", 2)).toBe("0.00");
    expect(formatDecimal("-12.5", 0)).toBe("-13");
  });
  it("trims trailing zeros for quantities", () => {
    expect(formatQty("12.500", "kg")).toBe("12.5 kg");
    expect(formatQty("40.000")).toBe("40");
  });
  it("shows timestamps in IST", () => {
    expect(formatIST("2026-10-17T18:45:00Z")).toContain("00:15");
  });
});

describe("inline validation mirrors backend rules", () => {
  it("quantity boundaries", () => {
    expect(checkQuantity("0", "kg")).not.toBeNull();
    expect(checkQuantity("0.001", "kg")).toBeNull();
    expect(checkQuantity("0.0001", "kg")).not.toBeNull();
    expect(checkQuantity("1.5", "pcs")).not.toBeNull();
    expect(checkQuantity("10000000", "kg")).toBeNull();
    expect(checkQuantity("10000000.001", "kg")).not.toBeNull();
    expect(checkQuantity("-2", "kg")).not.toBeNull();
    expect(checkQuantity("-2", "kg", { allowNegative: true })).toBeNull();
    expect(checkQuantity("abc", "kg")).not.toBeNull();
  });
  it("unit cost boundaries", () => {
    expect(checkUnitCost("0")).not.toBeNull();
    expect(checkUnitCost("-1")).not.toBeNull();
    expect(checkUnitCost("0.0001")).toBeNull();
    expect(checkUnitCost("1.00001")).not.toBeNull();
  });
  it("compares decimal strings exactly", () => {
    expect(compareMagnitude("5.001", "5")).toBe(1);
    expect(compareMagnitude("5.000", "5")).toBe(0);
    expect(compareMagnitude("0.1", "0.10000000001")).toBe(-1);
  });
});
