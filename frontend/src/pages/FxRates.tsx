import { useEffect, useMemo, useState } from "react";
import { NumericFormat } from "react-number-format";
import { api, downloadXlsx, errMsg } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { formatPlain } from "../format";

function todayStr() {
  return new Date().toISOString().slice(0, 10);
}

// Round 16: the fetch window's start date used to be this fixed constant
// ("generous" for a Jan-2026-onward import, but it silently capped every
// currency's history at 2020-01-01 -- once Round 15's historical import
// loaded real data back to 2010, that older history existed in the
// database but the page never even asked for it, so no period filter
// could reach it either). Replaced with a per-pair lookup via
// GET /api/fx/rates/earliest, so the fetch window always matches whatever
// data actually exists. This constant now only serves as a last-resort
// fallback when that lookup hasn't resolved yet or a pair has no data.
const NO_DATA_FALLBACK_START = todayStr();

interface CurrencyPair {
  id: number;
  base_currency: string;
  quote_currency: string;
  supports_extended_rates: boolean;
  is_default: boolean;
}

interface CombinedRow {
  rate_date: string;
  market_rate: string | null;
  market_id: number | null;
  market_carried_forward: boolean;
  cbos_rate: string | null;
  cbos_id: number | null;
  cbos_carried_forward: boolean;
  pricing_rate: string | null;
  pricing_id: number | null;
  pricing_carried_forward: boolean;
}

type FieldKey = "market" | "cbos" | "pricing";
const FIELDS: { key: FieldKey; label: string }[] = [
  { key: "market", label: "Market" },
  { key: "cbos", label: "CBOS" },
  { key: "pricing", label: "Pricing" },
];

function yearKey(dateStr: string) {
  return dateStr.slice(0, 4); // YYYY
}
function monthKey(dateStr: string) {
  return dateStr.slice(0, 7); // YYYY-MM
}
function monthLabel(key: string) {
  const [y, m] = key.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString("en-US", { month: "long", year: "numeric" });
}
function quarterKey(dateStr: string) {
  const [y, m] = dateStr.slice(0, 7).split("-").map(Number);
  return `${y}-Q${Math.floor((m - 1) / 3) + 1}`;
}
function quarterLabel(key: string) {
  const [y, q] = key.split("-Q");
  return `Q${q} ${y}`;
}

function avg(rows: CombinedRow[], field: `${FieldKey}_rate`): number | null {
  const vals = rows
    .map((r) => r[field])
    .filter((v): v is string => v !== null)
    .map(parseFloat)
    .filter((n) => !Number.isNaN(n));
  if (!vals.length) return null;
  return vals.reduce((a, b) => a + b, 0) / vals.length;
}

function fmtAvg(n: number | null): string {
  if (n === null) return "—";
  return formatPlain(n);
}

// International / cross-currency rates -- pairs where neither side is SDG
// (e.g. EUR/USD, USD/AED). These only ever get a Market rate (see
// NON_SDG_RATE_TYPES in config.py) and were previously not reachable from
// any UI at all -- the FX Rates page's currency selector above only lists
// SDG-quote pairs. This reuses the same single-pair endpoints the SDG
// tables use (/api/fx/rates, /rates/{id}, /rates/table); new pairs
// themselves are still added under Settings > Currency Pairs.
interface IntlRateRow {
  id: number | null;
  rate_date: string;
  rate: string;
}

function InternationalRatesSection({ pairs }: { pairs: CurrencyPair[] }) {
  const { canWrite } = useAuth();
  const intlPairs = useMemo(() => pairs.filter((p) => !p.supports_extended_rates), [pairs]);
  const [pairId, setPairId] = useState<number | "">("");
  const [rows, setRows] = useState<IntlRateRow[]>([]);
  const [loading, setLoading] = useState(false);
  // Round 16: fetch window start, resolved per-pair via /rates/earliest
  // instead of a fixed constant -- see the note on NO_DATA_FALLBACK_START.
  const [historyStart, setHistoryStart] = useState<string | null>(null);

  const [addDate, setAddDate] = useState(todayStr());
  const [addRate, setAddRate] = useState("");
  const [addBusy, setAddBusy] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  const [editingId, setEditingId] = useState<number | null>(null);
  const [editValue, setEditValue] = useState("");
  const [rowBusy, setRowBusy] = useState(false);
  const [rowError, setRowError] = useState<string | null>(null);

  useEffect(() => {
    if (pairId === "" && intlPairs.length > 0) setPairId(intlPairs[0].id);
  }, [intlPairs, pairId]);

  useEffect(() => {
    if (pairId === "") return;
    setHistoryStart(null);
    api
      .get<{ earliest: string | null }>("/api/fx/rates/earliest", { params: { currency_pair_id: pairId } })
      .then((res) => setHistoryStart(res.data.earliest ?? NO_DATA_FALLBACK_START));
  }, [pairId]);

  function load() {
    if (pairId === "" || !historyStart) return;
    setLoading(true);
    api
      .get<{ id: number | null; rate_date: string; rate: string }[]>("/api/fx/rates/table", {
        params: { currency_pair_id: pairId, rate_type: "Market", start: historyStart, end: todayStr() },
      })
      .then((res) =>
        setRows(
          res.data
            .filter((r) => r.id !== null)
            .map((r) => ({ id: r.id, rate_date: r.rate_date, rate: r.rate }))
            .sort((a, b) => b.rate_date.localeCompare(a.rate_date))
        )
      )
      .finally(() => setLoading(false));
  }

  useEffect(load, [pairId, historyStart]);

  async function addRow() {
    if (pairId === "" || !addDate || !addRate) return;
    setAddBusy(true);
    setAddError(null);
    try {
      await api.post("/api/fx/rates", {
        rate_date: addDate,
        currency_pair_id: pairId,
        rate_type: "Market",
        rate: addRate,
      });
      setAddRate("");
      load();
    } catch (e: any) {
      setAddError(errMsg(e, "Couldn't save this rate."));
    } finally {
      setAddBusy(false);
    }
  }

  function startEdit(r: IntlRateRow) {
    if (r.id === null) return;
    setEditingId(r.id);
    setEditValue(r.rate);
    setRowError(null);
  }

  async function saveEdit(id: number) {
    setRowBusy(true);
    setRowError(null);
    try {
      await api.patch(`/api/fx/rates/${id}`, { rate: editValue });
      setEditingId(null);
      load();
    } catch (e: any) {
      setRowError(errMsg(e, "Couldn't update this rate."));
    } finally {
      setRowBusy(false);
    }
  }

  async function deleteRow(r: IntlRateRow) {
    if (r.id === null) return;
    if (!window.confirm(`Delete the rate entered for ${r.rate_date}?`)) return;
    setRowError(null);
    try {
      await api.delete(`/api/fx/rates/${r.id}`);
      load();
    } catch (e: any) {
      setRowError(errMsg(e, "Couldn't delete this rate."));
    }
  }

  return (
    <div className="card">
      <h2 className="section-title">International Rates</h2>
      <p className="muted" style={{ marginTop: 0 }}>
        Cross-currency rates that don't involve SDG -- e.g. Euro/USD or USD/AED. These only take a
        single Market rate (no CBOS/Pricing split). Add a new pair under Settings &gt; Currency
        Pairs first if the one you need isn't listed below.
      </p>

      {intlPairs.length === 0 ? (
        <div className="empty-state">
          No international currency pairs yet -- add one under Settings &gt; Currency Pairs (pick
          two currencies, neither of which is SDG).
        </div>
      ) : (
        <>
          <div className="toolbar">
            <div className="filters">
              <select value={pairId} onChange={(e) => setPairId(Number(e.target.value))}>
                {intlPairs.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.base_currency}/{p.quote_currency}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {canWrite && (
            <div style={{ display: "flex", gap: "0.75rem", alignItems: "flex-end", marginBottom: "1rem" }}>
              <div>
                <label className="field-label">Date</label>
                <input type="date" value={addDate} onChange={(e) => setAddDate(e.target.value)} />
              </div>
              <div>
                <label className="field-label">Rate</label>
                <NumericFormat
                  thousandSeparator=","
                  decimalScale={4}
                  allowNegative={false}
                  value={addRate}
                  onValueChange={(v) => setAddRate(v.value)}
                />
              </div>
              <button className="btn btn--primary" disabled={!addDate || !addRate || addBusy} onClick={addRow}>
                {addBusy ? "Saving..." : "Add / Update"}
              </button>
            </div>
          )}
          {addError && <p className="error-text">{addError}</p>}
          {rowError && <p className="error-text">{rowError}</p>}

          {loading || !historyStart ? (
            <p className="muted">Loading...</p>
          ) : rows.length === 0 ? (
            <div className="empty-state">No rates recorded yet for this pair.</div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th className="numeric">Rate</th>
                  {canWrite && <th></th>}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.rate_date}>
                    <td>{r.rate_date}</td>
                    {editingId === r.id ? (
                      <td className="numeric">
                        <div style={{ display: "flex", gap: "0.35rem", alignItems: "center", justifyContent: "flex-end" }}>
                          <NumericFormat
                            style={{ textAlign: "right", width: 100 }}
                            thousandSeparator=","
                            decimalScale={4}
                            allowNegative={false}
                            value={editValue}
                            onValueChange={(v) => setEditValue(v.value)}
                          />
                          <button className="btn btn--small" onClick={() => saveEdit(r.id!)} disabled={rowBusy}>
                            Save
                          </button>
                          <button className="btn btn--small" onClick={() => setEditingId(null)} disabled={rowBusy}>
                            Cancel
                          </button>
                        </div>
                      </td>
                    ) : (
                      <td className="numeric">{formatPlain(r.rate)}</td>
                    )}
                    {canWrite && editingId !== r.id && (
                      <td>
                        <div className="row-actions">
                          <button className="btn btn--ghost btn--small" onClick={() => startEdit(r)}>
                            Edit
                          </button>
                          <button className="btn btn--danger btn--small" onClick={() => deleteRow(r)}>
                            Delete
                          </button>
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}

export function FxRates() {
  const { canWrite } = useAuth();
  const [pairs, setPairs] = useState<CurrencyPair[]>([]);
  const [currency, setCurrency] = useState<string>("");
  const [rows, setRows] = useState<CombinedRow[]>([]);
  const [loadingTable, setLoadingTable] = useState(false);

  const [periodType, setPeriodType] = useState<"All" | "Year" | "Quarter" | "Month">("All");
  const [periodValue, setPeriodValue] = useState<string>("");
  // Round 16: fetch window start, resolved per-currency via /rates/earliest
  // instead of a fixed constant -- see the note on NO_DATA_FALLBACK_START.
  const [historyStart, setHistoryStart] = useState<string | null>(null);

  const [batchDate, setBatchDate] = useState(todayStr());
  const [batchType, setBatchType] = useState<"Market" | "CBOS" | "Pricing">("Market");
  const [usdRate, setUsdRate] = useState("");
  const [euroRate, setEuroRate] = useState("");
  const [aedRate, setAedRate] = useState("");
  const [batchBusy, setBatchBusy] = useState(false);
  const [batchError, setBatchError] = useState<string | null>(null);
  const [batchOk, setBatchOk] = useState<string | null>(null);

  // Round 13: for Market rates only, USD and Euro are derived from the
  // entered AED rate via the International Rates pairs (USD/AED, EUR/USD)
  // rather than typed in directly -- CBOS/Pricing keep manual 3-field entry
  // since those don't have an equivalent international-rate source.
  const [calcBusy, setCalcBusy] = useState(false);
  const [calcError, setCalcError] = useState<string | null>(null);
  const [calcInfo, setCalcInfo] = useState<string | null>(null);
  const isMarketAutoCalc = batchType === "Market";

  const [editing, setEditing] = useState<{ date: string; field: FieldKey } | null>(null);
  const [editValue, setEditValue] = useState("");
  const [rowBusy, setRowBusy] = useState(false);
  const [rowError, setRowError] = useState<string | null>(null);

  const sdgPairCurrencies = useMemo(
    () => pairs.filter((p) => p.supports_extended_rates && p.quote_currency === "SDG").map((p) => p.base_currency),
    [pairs]
  );

  useEffect(() => {
    api.get<CurrencyPair[]>("/api/settings/currency-pairs").then((res) => setPairs(res.data));
  }, []);

  useEffect(() => {
    if (currency || sdgPairCurrencies.length === 0) return;
    setCurrency(sdgPairCurrencies.includes("AED") ? "AED" : sdgPairCurrencies[0]);
  }, [sdgPairCurrencies, currency]);

  useEffect(() => {
    if (!currency) return;
    setHistoryStart(null);
    api
      .get<{ earliest: string | null }>("/api/fx/rates/earliest", { params: { currency } })
      .then((res) => setHistoryStart(res.data.earliest ?? NO_DATA_FALLBACK_START));
  }, [currency]);

  function loadTable() {
    if (!currency || !historyStart) return;
    setLoadingTable(true);
    return api
      .get<CombinedRow[]>("/api/fx/rates/combined", {
        params: { currency, start: historyStart, end: todayStr() },
      })
      .then((res) => setRows(res.data))
      .finally(() => setLoadingTable(false));
  }

  useEffect(() => {
    loadTable();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currency, historyStart]);

  useEffect(() => {
    if (!isMarketAutoCalc) {
      setCalcError(null);
      setCalcInfo(null);
      return;
    }
    if (!aedRate || !batchDate) {
      setUsdRate("");
      setEuroRate("");
      setCalcError(null);
      setCalcInfo(null);
      return;
    }
    const usdAedPair = pairs.find((p) => p.base_currency === "USD" && p.quote_currency === "AED");
    const eurUsdPair = pairs.find((p) => p.base_currency === "EUR" && p.quote_currency === "USD");
    if (!usdAedPair || !eurUsdPair) {
      setCalcError(
        "USD/AED and EUR/USD international pairs must exist first -- add them under Settings > Currency Pairs."
      );
      setUsdRate("");
      setEuroRate("");
      return;
    }
    setCalcBusy(true);
    setCalcError(null);
    Promise.all([
      api.get<{ rate: string }[]>("/api/fx/rates/table", {
        params: { currency_pair_id: usdAedPair.id, rate_type: "Market", start: batchDate, end: batchDate },
      }),
      api.get<{ rate: string }[]>("/api/fx/rates/table", {
        params: { currency_pair_id: eurUsdPair.id, rate_type: "Market", start: batchDate, end: batchDate },
      }),
    ])
      .then(([usdAedRes, eurUsdRes]) => {
        const usdAed = usdAedRes.data[0]?.rate;
        const eurUsd = eurUsdRes.data[0]?.rate;
        if (!usdAed || !eurUsd) {
          setCalcError(
            "No USD/AED or EUR/USD International Rate on file on or before this date yet -- add one under" +
              " International Rates below first."
          );
          setUsdRate("");
          setEuroRate("");
          return;
        }
        const aed = parseFloat(aedRate);
        const usdAedNum = parseFloat(usdAed);
        const eurUsdNum = parseFloat(eurUsd);
        const usd = aed * usdAedNum;
        const euro = eurUsdNum * usd;
        setUsdRate(usd.toFixed(4));
        setEuroRate(euro.toFixed(4));
        setCalcInfo(`Calculated from USD/AED ${usdAedNum.toFixed(4)} and EUR/USD ${eurUsdNum.toFixed(4)}.`);
      })
      .catch(() => setCalcError("Couldn't calculate USD/Euro rates from the international pairs."))
      .finally(() => setCalcBusy(false));
  }, [isMarketAutoCalc, aedRate, batchDate, pairs]);

  async function saveBatch() {
    if (!batchDate || !usdRate || !euroRate || !aedRate) return;
    setBatchBusy(true);
    setBatchError(null);
    setBatchOk(null);
    try {
      await api.post("/api/fx/rates/batch", {
        rate_date: batchDate,
        rate_type: batchType,
        usd_rate: usdRate,
        euro_rate: euroRate,
        aed_rate: aedRate,
      });
      setBatchOk(`Saved ${batchType} rates for ${batchDate}.`);
      setUsdRate("");
      setEuroRate("");
      setAedRate("");
      loadTable();
      // If a new currency pair was auto-created (USD/EUR/SDG on first use),
      // the currency selector needs to know about it too.
      api.get<CurrencyPair[]>("/api/settings/currency-pairs").then((res) => setPairs(res.data));
    } catch (e: any) {
      setBatchError(errMsg(e, "Couldn't save these rates."));
    } finally {
      setBatchBusy(false);
    }
  }

  function startEdit(r: CombinedRow, field: FieldKey) {
    const id = field === "market" ? r.market_id : field === "cbos" ? r.cbos_id : r.pricing_id;
    if (!id) return;
    const current = field === "market" ? r.market_rate : field === "cbos" ? r.cbos_rate : r.pricing_rate;
    setEditing({ date: r.rate_date, field });
    setEditValue(current ?? "");
    setRowError(null);
  }

  async function saveEdit(r: CombinedRow) {
    if (!editing) return;
    const id = editing.field === "market" ? r.market_id : editing.field === "cbos" ? r.cbos_id : r.pricing_id;
    if (!id) return;
    setRowBusy(true);
    setRowError(null);
    try {
      await api.patch(`/api/fx/rates/${id}`, { rate: editValue });
      setEditing(null);
      loadTable();
    } catch (e: any) {
      setRowError(errMsg(e, "Couldn't update this rate."));
    } finally {
      setRowBusy(false);
    }
  }

  async function deleteCell(r: CombinedRow, field: FieldKey) {
    const id = field === "market" ? r.market_id : field === "cbos" ? r.cbos_id : r.pricing_id;
    if (!id) return;
    const fieldLabel = FIELDS.find((f) => f.key === field)!.label;
    if (
      !window.confirm(
        `Delete the ${fieldLabel} rate entered for ${r.rate_date}? Later dates will fall back to carrying forward the next earlier entry.`
      )
    )
      return;
    setRowError(null);
    try {
      await api.delete(`/api/fx/rates/${id}`);
      loadTable();
    } catch (e: any) {
      setRowError(errMsg(e, "Couldn't delete this rate."));
    }
  }

  // Round 16: Year sits between "All" and "Quarter" -- once the fetch
  // window actually reaches back to 2010 (see historyStart above), the
  // Quarter/Month dropdowns alone are unwieldy for jumping to an old year,
  // which is exactly the gap the user pointed out after the Round 15
  // historical import landed.
  const years = useMemo(
    () => Array.from(new Set(rows.map((r) => yearKey(r.rate_date)))).sort().reverse(),
    [rows]
  );
  const quarters = useMemo(
    () => Array.from(new Set(rows.map((r) => quarterKey(r.rate_date)))).sort().reverse(),
    [rows]
  );
  const monthsAvailable = useMemo(
    () => Array.from(new Set(rows.map((r) => monthKey(r.rate_date)))).sort().reverse(),
    [rows]
  );

  useEffect(() => {
    if (periodType === "Year" && !years.includes(periodValue)) setPeriodValue(years[0] ?? "");
    if (periodType === "Quarter" && !quarters.includes(periodValue)) setPeriodValue(quarters[0] ?? "");
    if (periodType === "Month" && !monthsAvailable.includes(periodValue)) setPeriodValue(monthsAvailable[0] ?? "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [periodType, years, quarters, monthsAvailable]);

  const filteredRows = useMemo(() => {
    if (periodType === "All") return rows;
    if (periodType === "Year") return rows.filter((r) => yearKey(r.rate_date) === periodValue);
    if (periodType === "Quarter") return rows.filter((r) => quarterKey(r.rate_date) === periodValue);
    return rows.filter((r) => monthKey(r.rate_date) === periodValue);
  }, [rows, periodType, periodValue]);

  // Round 13 fix: this used to build from the unfiltered `rows`, so
  // selecting Quarter/Month only narrowed the 3 average stat cards above --
  // the actual table ignored the period filter entirely. Building from
  // `filteredRows` instead makes the filter apply everywhere it's shown.
  const byMonth = useMemo(() => {
    const m = new Map<string, CombinedRow[]>();
    for (const r of filteredRows) {
      const k = monthKey(r.rate_date);
      if (!m.has(k)) m.set(k, []);
      m.get(k)!.push(r);
    }
    return m;
  }, [filteredRows]);
  const monthKeys = Array.from(byMonth.keys()).sort().reverse();
  const currentMonthKey = todayStr().slice(0, 7);
  // When a specific Quarter/Month is picked, every group in view is exactly
  // what was asked for -- show it expanded rather than collapsed into
  // <details>, which only makes sense for "All" (where every month besides
  // the current one is historical noise by default).
  const alwaysExpand = periodType !== "All";

  function cell(r: CombinedRow, field: FieldKey) {
    const rate = field === "market" ? r.market_rate : field === "cbos" ? r.cbos_rate : r.pricing_rate;
    const id = field === "market" ? r.market_id : field === "cbos" ? r.cbos_id : r.pricing_id;
    const carried =
      field === "market" ? r.market_carried_forward : field === "cbos" ? r.cbos_carried_forward : r.pricing_carried_forward;

    if (editing && editing.date === r.rate_date && editing.field === field) {
      return (
        <td className="numeric" key={field}>
          <div style={{ display: "flex", gap: "0.35rem", alignItems: "center", justifyContent: "flex-end" }}>
            <NumericFormat
              style={{ textAlign: "right", width: 100 }}
              thousandSeparator=","
              decimalScale={4}
              allowNegative={false}
              value={editValue}
              onValueChange={(v) => setEditValue(v.value)}
            />
            <button className="btn btn--small" onClick={() => saveEdit(r)} disabled={rowBusy}>
              Save
            </button>
            <button className="btn btn--small" onClick={() => setEditing(null)} disabled={rowBusy}>
              Cancel
            </button>
          </div>
        </td>
      );
    }

    return (
      <td className={"numeric" + (carried ? " is-carried-forward" : "")} key={field}>
        {rate === null ? (
          <span className="muted">—</span>
        ) : (
          <span title={carried ? "Carried forward from an earlier entry" : "Entered"}>{formatPlain(rate)}</span>
        )}
        {canWrite && id && (
          <span className="row-actions" style={{ marginLeft: "0.5rem" }}>
            <button className="btn btn--ghost btn--small" onClick={() => startEdit(r, field)}>
              Edit
            </button>
            <button className="btn btn--danger btn--small" onClick={() => deleteCell(r, field)}>
              Delete
            </button>
          </span>
        )}
      </td>
    );
  }

  function table(tableRows: CombinedRow[]) {
    return (
      <table className="data-table">
        <thead>
          <tr>
            <th>Date</th>
            <th className="numeric">Market</th>
            <th className="numeric">CBOS</th>
            <th className="numeric">Pricing</th>
          </tr>
        </thead>
        <tbody>
          {tableRows
            .slice()
            .sort((a, b) => b.rate_date.localeCompare(a.rate_date))
            .map((r) => (
              <tr key={r.rate_date}>
                <td>{r.rate_date}</td>
                {cell(r, "market")}
                {cell(r, "cbos")}
                {cell(r, "pricing")}
              </tr>
            ))}
          {tableRows.length === 0 && (
            <tr>
              <td className="muted" colSpan={4}>
                No rates recorded yet for this currency/period.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    );
  }

  return (
    <div className="page">
      <div className="page__header">
        <h1 className="page__title">FX Rates</h1>
        <p className="page__subtitle">
          Market, CBOS and Pricing rates for the selected currency, side by side. Gaps between
          entries are automatically carried forward from the last known rate.
        </p>
      </div>

      {canWrite && (
        <div className="card">
          <h2 className="section-title">Add / Update Rates</h2>
          <p className="muted" style={{ marginTop: 0, marginBottom: "1rem" }}>
            {isMarketAutoCalc
              ? "For Market rates, only the AED rate is entered -- USD and Euro are calculated" +
                " automatically from the USD/AED and EUR/USD International Rates (below) for this date."
              : "USD, Euro and AED are saved together as one entry -- all three are required, whichever" +
                " rate type you're recording."}
          </p>
          <div className="form-grid" style={{ maxWidth: 720 }}>
            <div>
              <label className="field-label">Rate Type</label>
              <select value={batchType} onChange={(e) => setBatchType(e.target.value as any)}>
                <option value="Market">Market</option>
                <option value="CBOS">CBOS</option>
                <option value="Pricing">Pricing</option>
              </select>
            </div>
            <div>
              <label className="field-label">Date</label>
              <input type="date" value={batchDate} onChange={(e) => setBatchDate(e.target.value)} />
            </div>
            <div>
              <label className="field-label">AED Rate</label>
              <NumericFormat
                thousandSeparator=","
                decimalScale={4}
                allowNegative={false}
                value={aedRate}
                onValueChange={(v) => setAedRate(v.value)}
              />
            </div>
            <div>
              <label className="field-label">USD Rate{isMarketAutoCalc ? " (calculated)" : ""}</label>
              <NumericFormat
                thousandSeparator=","
                decimalScale={4}
                allowNegative={false}
                value={usdRate}
                disabled={isMarketAutoCalc}
                onValueChange={(v) => setUsdRate(v.value)}
              />
            </div>
            <div>
              <label className="field-label">Euro Rate{isMarketAutoCalc ? " (calculated)" : ""}</label>
              <NumericFormat
                thousandSeparator=","
                decimalScale={4}
                allowNegative={false}
                value={euroRate}
                disabled={isMarketAutoCalc}
                onValueChange={(v) => setEuroRate(v.value)}
              />
            </div>
          </div>
          {isMarketAutoCalc && calcBusy && <p className="muted">Calculating...</p>}
          {isMarketAutoCalc && calcError && <p className="error-text">{calcError}</p>}
          {isMarketAutoCalc && calcInfo && !calcError && <p className="muted">{calcInfo}</p>}
          <button
            className="btn btn--primary"
            style={{ marginTop: "0.75rem" }}
            disabled={!batchDate || !usdRate || !euroRate || !aedRate || batchBusy || (isMarketAutoCalc && !!calcError)}
            onClick={saveBatch}
          >
            {batchBusy ? "Saving..." : "Save Rates"}
          </button>
          {batchError && <p className="error-text">{batchError}</p>}
          {batchOk && <p className="muted">{batchOk}</p>}
        </div>
      )}

      <div className="card">
        <div className="toolbar">
          <h2 className="section-title" style={{ marginBottom: 0 }}>
            Rate History
          </h2>
          <div className="filters">
            <select value={currency} onChange={(e) => setCurrency(e.target.value)}>
              {sdgPairCurrencies.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
            <select value={periodType} onChange={(e) => setPeriodType(e.target.value as any)}>
              <option value="All">All</option>
              <option value="Year">Year</option>
              <option value="Quarter">Quarter</option>
              <option value="Month">Month</option>
            </select>
            {periodType === "Year" && (
              <select value={periodValue} onChange={(e) => setPeriodValue(e.target.value)}>
                {years.map((y) => (
                  <option key={y} value={y}>
                    {y}
                  </option>
                ))}
              </select>
            )}
            {periodType === "Quarter" && (
              <select value={periodValue} onChange={(e) => setPeriodValue(e.target.value)}>
                {quarters.map((q) => (
                  <option key={q} value={q}>
                    {quarterLabel(q)}
                  </option>
                ))}
              </select>
            )}
            {periodType === "Month" && (
              <select value={periodValue} onChange={(e) => setPeriodValue(e.target.value)}>
                {monthsAvailable.map((m) => (
                  <option key={m} value={m}>
                    {monthLabel(m)}
                  </option>
                ))}
              </select>
            )}
            <button
              className="btn btn--ghost"
              disabled={filteredRows.length === 0}
              onClick={() => {
                const dates = filteredRows.map((r) => r.rate_date).sort();
                const start = dates[0] || historyStart || NO_DATA_FALLBACK_START;
                const end = dates[dates.length - 1] || todayStr();
                downloadXlsx("/api/fx/rates/combined/export", `fx_rate_history_${currency}.xlsx`, {
                  currency,
                  start,
                  end,
                });
              }}
            >
              Download as Excel
            </button>
          </div>
        </div>

        <div className="stat-grid" style={{ marginBottom: "1rem" }}>
          <div className="stat-card">
            <p className="stat-card__label">
              Market Average ({
                periodType === "All"
                  ? "All data"
                  : periodType === "Year"
                  ? periodValue || ""
                  : periodType === "Quarter"
                  ? quarterLabel(periodValue || "")
                  : monthLabel(periodValue || "")
              })
            </p>
            <p className="stat-card__value">{fmtAvg(avg(filteredRows, "market_rate"))}</p>
          </div>
          <div className="stat-card">
            <p className="stat-card__label">CBOS Average</p>
            <p className="stat-card__value">{fmtAvg(avg(filteredRows, "cbos_rate"))}</p>
          </div>
          <div className="stat-card">
            <p className="stat-card__label">Pricing Average</p>
            <p className="stat-card__value">{fmtAvg(avg(filteredRows, "pricing_rate"))}</p>
          </div>
        </div>

        {rowError && <p className="error-text">{rowError}</p>}

        {loadingTable || !historyStart ? (
          <p className="muted">Loading...</p>
        ) : monthKeys.length === 0 ? (
          <div className="empty-state">No rates recorded yet for this currency.</div>
        ) : (
          monthKeys.map((m) => {
            const monthRows = byMonth.get(m)!;
            const isCurrent = alwaysExpand || m === currentMonthKey;
            const summaryLine = (
              <p className="muted" style={{ fontSize: "0.82rem", margin: "0 0 0.5rem" }}>
                Averages for {monthLabel(m)}: Market {fmtAvg(avg(monthRows, "market_rate"))} · CBOS{" "}
                {fmtAvg(avg(monthRows, "cbos_rate"))} · Pricing {fmtAvg(avg(monthRows, "pricing_rate"))}
              </p>
            );
            return isCurrent ? (
              <div key={m} style={{ marginBottom: "1rem" }}>
                <p className="section-title" style={{ fontSize: "0.95rem" }}>
                  {monthLabel(m)}
                </p>
                {summaryLine}
                {table(monthRows)}
              </div>
            ) : (
              <details className="month-group" key={m}>
                <summary>{monthLabel(m)}</summary>
                <div style={{ padding: "0 1rem 0.75rem" }}>
                  {summaryLine}
                  {table(monthRows)}
                </div>
              </details>
            );
          })
        )}
      </div>

      <InternationalRatesSection pairs={pairs} />
    </div>
  );
}
