import { useEffect, useState } from "react";
import { NumericFormat } from "react-number-format";
import { api, downloadXlsx } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { formatPlain } from "../format";

function todayStr() {
  return new Date().toISOString().slice(0, 10);
}

interface CurrencyPair {
  id: number;
  base_currency: string;
  quote_currency: string;
  supports_extended_rates: boolean;
  is_default: boolean;
}

interface FxRateRow {
  id: number | null;
  rate_date: string;
  currency_pair: string;
  rate_type: string;
  rate: string;
  is_carried_forward: boolean;
}

interface ImportResult {
  imported: number;
  updated: number;
  skipped: { row_number: number; reason: string }[];
}

function monthKey(dateStr: string) {
  return dateStr.slice(0, 7); // YYYY-MM
}

function monthLabel(key: string) {
  const [y, m] = key.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString("en-US", { month: "long", year: "numeric" });
}

export function FxRates() {
  const { canWrite } = useAuth();
  const [pairs, setPairs] = useState<CurrencyPair[]>([]);
  const [pairId, setPairId] = useState<number | null>(null);
  const [rateType, setRateType] = useState("Market");
  const [availableTypes, setAvailableTypes] = useState<string[]>(["Market"]);
  const [rows, setRows] = useState<FxRateRow[]>([]);
  const [loadingTable, setLoadingTable] = useState(false);

  const [file, setFile] = useState<File | null>(null);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  const [importError, setImportError] = useState<string | null>(null);

  const [entryDate, setEntryDate] = useState(todayStr());
  const [entryRate, setEntryRate] = useState("");
  const [entryBusy, setEntryBusy] = useState(false);
  const [entryError, setEntryError] = useState<string | null>(null);

  const [editingDate, setEditingDate] = useState<string | null>(null);
  const [editRate, setEditRate] = useState("");
  const [rowBusy, setRowBusy] = useState(false);
  const [rowError, setRowError] = useState<string | null>(null);

  useEffect(() => {
    api.get<CurrencyPair[]>("/api/settings/currency-pairs").then((res) => {
      setPairs(res.data);
      const def = res.data.find((p) => p.is_default) || res.data[0];
      if (def) setPairId(def.id);
    });
  }, []);

  useEffect(() => {
    if (pairId == null) return;
    const pair = pairs.find((p) => p.id === pairId);
    const types = pair?.supports_extended_rates ? ["Market", "CBOS", "Pricing"] : ["Market"];
    setAvailableTypes(types);
    if (!types.includes(rateType)) setRateType(types[0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pairId, pairs]);

  function loadTable() {
    if (pairId == null) return;
    setLoadingTable(true);
    const end = new Date();
    const start = new Date();
    start.setMonth(start.getMonth() - 6);
    const fmt = (d: Date) => d.toISOString().slice(0, 10);
    return api
      .get<FxRateRow[]>("/api/fx/rates/table", {
        params: {
          currency_pair_id: pairId,
          rate_type: rateType,
          start: fmt(start),
          end: fmt(end),
        },
      })
      .then((res) => setRows(res.data))
      .finally(() => setLoadingTable(false));
  }

  useEffect(() => {
    loadTable();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pairId, rateType, importResult]);

  async function addOrUpdateRate() {
    if (pairId == null || !entryDate || !entryRate) return;
    setEntryBusy(true);
    setEntryError(null);
    try {
      await api.post("/api/fx/rates", {
        rate_date: entryDate,
        currency_pair_id: pairId,
        rate_type: rateType,
        rate: entryRate,
      });
      setEntryRate("");
      loadTable();
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setEntryError(typeof detail === "string" && detail ? detail : "Couldn't save this rate.");
    } finally {
      setEntryBusy(false);
    }
  }

  function startEdit(r: FxRateRow) {
    setEditingDate(r.rate_date);
    setEditRate(r.rate);
    setRowError(null);
  }

  async function saveRowEdit(r: FxRateRow) {
    if (!r.id) return;
    setRowBusy(true);
    setRowError(null);
    try {
      await api.patch(`/api/fx/rates/${r.id}`, { rate: editRate });
      setEditingDate(null);
      loadTable();
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setRowError(typeof detail === "string" && detail ? detail : "Couldn't update this rate.");
    } finally {
      setRowBusy(false);
    }
  }

  async function deleteRow(r: FxRateRow) {
    if (!r.id) return;
    if (!window.confirm(`Delete the ${r.rate_type} rate entered for ${r.rate_date}? Later dates will fall back to carrying forward the next earlier entry.`))
      return;
    setRowError(null);
    try {
      await api.delete(`/api/fx/rates/${r.id}`);
      loadTable();
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setRowError(typeof detail === "string" && detail ? detail : "Couldn't delete this rate.");
    }
  }

  async function handleDownloadTemplate() {
    await downloadXlsx("/api/fx/import/template", "fx_rates_template.xlsx");
  }

  async function handleImport() {
    if (!file) return;
    setImporting(true);
    setImportError(null);
    setImportResult(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await api.post<ImportResult>("/api/fx/import", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setImportResult(res.data);
      setFile(null);
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setImportError(
        typeof detail === "string" && detail
          ? detail
          : detail
          ? JSON.stringify(detail)
          : "Import failed -- the server didn't say why. Try again, and if it keeps happening, send this file over."
      );
    } finally {
      setImporting(false);
    }
  }

  const byMonth = new Map<string, FxRateRow[]>();
  for (const r of rows) {
    const k = monthKey(r.rate_date);
    if (!byMonth.has(k)) byMonth.set(k, []);
    byMonth.get(k)!.push(r);
  }
  const months = Array.from(byMonth.keys()).sort().reverse();
  const currentMonthKey = new Date().toISOString().slice(0, 7);

  return (
    <div className="page">
      <div className="page__header">
        <h1 className="page__title">FX Rates</h1>
        <p className="page__subtitle">
          Market, CBOS and Pricing rates. Gaps between entries are automatically carried
          forward from the last known rate.
        </p>
      </div>

      {canWrite && (
        <div className="card">
          <h2 className="section-title">Import Rates from Excel</h2>
          <p className="muted" style={{ marginTop: 0, marginBottom: "1rem" }}>
            Upload rates in bulk. Re-uploading a Date + Pair + Rate Type that already exists
            updates it — use this to replace test data with final figures.
          </p>
          <div className="toolbar">
            <div className="filters">
              <button className="btn btn--ghost" onClick={handleDownloadTemplate}>
                Download Template
              </button>
              <input
                type="file"
                accept=".xlsx"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
              <button className="btn btn--primary" disabled={!file || importing} onClick={handleImport}>
                {importing ? "Uploading..." : "Upload"}
              </button>
            </div>
          </div>
          {importError && <p className="error-text">{importError}</p>}
          {importResult && (
            <div className={"alert " + (importResult.skipped.length ? "alert--neutral" : "alert--positive")}>
              Imported {importResult.imported} new rate(s), updated {importResult.updated}.
              {importResult.skipped.length > 0 && (
                <>
                  {" "}
                  {importResult.skipped.length} row(s) skipped:
                  <ul style={{ margin: "0.5rem 0 0", paddingLeft: "1.2rem" }}>
                    {importResult.skipped.map((s) => (
                      <li key={s.row_number}>
                        Row {s.row_number}: {s.reason}
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          )}
        </div>
      )}

      {canWrite && (
        <div className="card">
          <h2 className="section-title">Add / Update a Rate</h2>
          <p className="muted" style={{ marginTop: 0, marginBottom: "1rem" }}>
            Enter today's (or any day's) rate directly -- this is the day-to-day way to keep
            rates current without building a spreadsheet. Uses the pair and rate type selected
            in Rate History below. Saving a date that already has a rate updates it.
          </p>
          <div className="form-grid" style={{ maxWidth: 560 }}>
            <div>
              <label className="field-label">Date</label>
              <input type="date" value={entryDate} onChange={(e) => setEntryDate(e.target.value)} />
            </div>
            <div>
              <label className="field-label">
                Rate ({pairs.find((p) => p.id === pairId)?.base_currency}/
                {pairs.find((p) => p.id === pairId)?.quote_currency}, {rateType})
              </label>
              <NumericFormat
                thousandSeparator=","
                decimalScale={4}
                allowNegative={false}
                value={entryRate}
                onValueChange={(v) => setEntryRate(v.value)}
              />
            </div>
          </div>
          <button
            className="btn btn--primary"
            style={{ marginTop: "0.75rem" }}
            disabled={pairId == null || !entryDate || !entryRate || entryBusy}
            onClick={addOrUpdateRate}
          >
            {entryBusy ? "Saving..." : "Save Rate"}
          </button>
          {entryError && <p className="error-text">{entryError}</p>}
        </div>
      )}

      <div className="card">
        <div className="toolbar">
          <h2 className="section-title" style={{ marginBottom: 0 }}>
            Rate History
          </h2>
          <div className="filters">
            <select value={pairId ?? ""} onChange={(e) => setPairId(Number(e.target.value))}>
              {pairs.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.base_currency}/{p.quote_currency}
                </option>
              ))}
            </select>
            <select value={rateType} onChange={(e) => setRateType(e.target.value)}>
              {availableTypes.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <a href="#" onClick={(e) => { e.preventDefault(); downloadXlsx(
              `/api/fx/rates/table/export?currency_pair_id=${pairId}&rate_type=${rateType}&start=${new Date(new Date().setMonth(new Date().getMonth()-6)).toISOString().slice(0,10)}&end=${new Date().toISOString().slice(0,10)}`,
              "fx_rates.xlsx"
            ); }} className="btn btn--ghost">
              Download as Excel
            </a>
          </div>
        </div>

        {rowError && <p className="error-text">{rowError}</p>}

        {loadingTable ? (
          <p className="muted">Loading...</p>
        ) : months.length === 0 ? (
          <div className="empty-state">No rates recorded yet for this pair/type.</div>
        ) : (
          months.map((m) => {
            const monthRows = byMonth.get(m)!.slice().sort((a, b) => b.rate_date.localeCompare(a.rate_date));
            const isCurrent = m === currentMonthKey;
            const table = (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th className="numeric">Rate</th>
                    <th>Source</th>
                    {canWrite && <th></th>}
                  </tr>
                </thead>
                <tbody>
                  {monthRows.map((r) =>
                    editingDate === r.rate_date && r.id ? (
                      <tr key={r.rate_date}>
                        <td>{r.rate_date}</td>
                        <td className="numeric">
                          <NumericFormat
                            style={{ textAlign: "right" }}
                            thousandSeparator=","
                            decimalScale={4}
                            allowNegative={false}
                            value={editRate}
                            onValueChange={(v) => setEditRate(v.value)}
                          />
                        </td>
                        <td>Entered</td>
                        <td>
                          <div className="row-actions">
                            <button className="btn btn--small" onClick={() => saveRowEdit(r)} disabled={rowBusy}>
                              Save
                            </button>
                            <button className="btn btn--small" onClick={() => setEditingDate(null)} disabled={rowBusy}>
                              Cancel
                            </button>
                          </div>
                        </td>
                      </tr>
                    ) : (
                      <tr key={r.rate_date} className={r.is_carried_forward ? "is-carried-forward" : ""}>
                        <td>{r.rate_date}</td>
                        <td className="numeric">{formatPlain(r.rate)}</td>
                        <td>{r.is_carried_forward ? "Carried forward" : "Entered"}</td>
                        {canWrite && (
                          <td>
                            {r.id && (
                              <div className="row-actions">
                                <button className="btn btn--ghost btn--small" onClick={() => startEdit(r)}>
                                  Edit
                                </button>
                                <button className="btn btn--danger btn--small" onClick={() => deleteRow(r)}>
                                  Delete
                                </button>
                              </div>
                            )}
                          </td>
                        )}
                      </tr>
                    )
                  )}
                </tbody>
              </table>
            );
            return isCurrent ? (
              <div key={m} style={{ marginBottom: "1rem" }}>
                <p className="section-title" style={{ fontSize: "0.95rem" }}>{monthLabel(m)}</p>
                {table}
              </div>
            ) : (
              <details className="month-group" key={m}>
                <summary>{monthLabel(m)}</summary>
                <div style={{ padding: "0 1rem 0.75rem" }}>{table}</div>
              </details>
            );
          })
        )}
      </div>
    </div>
  );
}
