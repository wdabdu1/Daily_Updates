function sdgFormatter(decimals: number) {
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function usdFormatter(decimals: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export function formatSDG(value: number | string | null | undefined, decimals = 2): string {
  if (value === null || value === undefined) return "—";
  const n = typeof value === "string" ? parseFloat(value) : value;
  if (Number.isNaN(n)) return "—";
  return `${sdgFormatter(decimals).format(n)} SDG`;
}

export function formatUSD(value: number | string | null | undefined, decimals = 2): string {
  if (value === null || value === undefined) return "—";
  const n = typeof value === "string" ? parseFloat(value) : value;
  if (Number.isNaN(n)) return "—";
  return usdFormatter(decimals).format(n);
}

// Thousands-grouped whole number, no currency suffix -- for tables where
// space is tight and the unit is already conveyed by the column/section
// header rather than repeated on every cell (e.g. the Division Receivables
// history table).
export function formatWhole(value: number | string | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const n = typeof value === "string" ? parseFloat(value) : value;
  if (Number.isNaN(n)) return "—";
  return Math.round(n).toLocaleString("en-US");
}

export function formatPct(value: number | string | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const n = typeof value === "string" ? parseFloat(value) : value;
  if (Number.isNaN(n)) return "—";
  return `${n > 0 ? "+" : ""}${n.toFixed(2)}%`;
}

export function formatPlain(value: number | string | null | undefined, decimals = 4): string {
  if (value === null || value === undefined) return "—";
  const n = typeof value === "string" ? parseFloat(value) : value;
  if (Number.isNaN(n)) return "—";
  return n.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}
