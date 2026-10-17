import { useState } from "react";

// There is no login (README assumption): the operator types their name once and it is sent
// as created_by on every movement. Stored per browser only as a convenience.
const KEY = "stock-ledger.operator";

function read(): string {
  try {
    return localStorage.getItem(KEY) ?? "";
  } catch {
    return "";
  }
}

export function useOperator(): [string, (name: string) => void] {
  const [name, setName] = useState(read);
  const update = (value: string) => {
    setName(value);
    try {
      localStorage.setItem(KEY, value);
    } catch {
      /* private mode: keep it in memory only */
    }
  };
  return [name, update];
}
