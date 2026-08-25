import { useEffect, useState } from "react";
import { NumericFormat } from "react-number-format";
import { api, downloadXlsx } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { formatSDG } from "../format";

interface BankDue {
  id: number;
  account_id: number;
  due_date: string | null;
  facility_type: string | null;
  amount: string;
  status: string;
  business_unit_name: string | null;
  division_name: string | null;
  bank_short_name: string | null;
  account_number: string | null;
}

interface ImportResult {
  imported: number;
  updated: number;
  skipped: { row_number: number; reason: string }[];
}

interface ReceivableFormRow {
  account_id: number;
  business_unit_name: string;
  division_name: string;
  bank_short_name: string;
  account_name: string;
  account_number: string;
  currency: string;
  default_amount: string;
  default_amount_date: string | null;
}

function DuesSection() {
  const { canWrite } = useAuth();
  const [dues, setDues] = useState<BankDue[]>([]);
  const [loading, setLoading] = useState(true);
  const [file, setFile] = useState<File | null>(null);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  const [importError, setImportError] = useState<string | null>(null);

  function refresh() {
    setLoading(true);
    api
      .get<BankDue[]>("/api/dues")
      .then((res) => setDues(res.data))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  async function handleImport() {
    if (!file) return;
    setImporting(true);
    setImportError(null);
    setImportResult(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await api.post<ImportResult>("/api/dues/import", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setImportResult(res.data);
      setFile(null);
      refresh();
    } catch (e: any) {
      setImportError(e?.response?.data?.detail || "Import failed.");
    } finally {
      setImporting(false);
    }
  }

  async function settle(id: number) {
    await api.post(`/api/dues/${id}/settle`);
    refresh();
  }

  return (
    <div className="card">
      <h2 className="section-title">Bank Dues</h2>

      {canWrite && (
        <>
          <p className="muted" style={{ marginTop: 0 }}>
            Upload dues in bulk. Accounts referenced that don't exist yet (Business Unit,
            Division, Bank, Account Number) are created automatically. Re-uploading the same
            account + due date + facility type updates the amount/status instead of duplicating.
          </p>
          <div className="toolbar">
            <div className="filters">
              <button
                className="btn btn--ghost"
                onClick={() => downloadXlsx("/api/dues/import/template", "bank_dues_template.xlsx")}
              >
                Download Template
              </button>
              <input type="file" accept=".xlsx" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
              <button className="btn btn--primary" disabled={!file || importing} onClick={handleImport}>
                {importing ? "Uploading..." : "Upload"}
              </button>
              <button
                className="btn btn--ghost"
                onClick={() => downloadXlsx("/api/dues/export", "bank_dues.xlsx")}
              >
                Download as Excel
              </button>
            </div>
          </div>
          {importError && <p className="error-text">{importError}</p>}
          {importResult && (
            <div className={"alert " + (importResult.skipped.length ? "alert--neutral" : "alert--positive")}>
              Imported {importResult.imported} new due(s), updated {importResult.updated}.
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
        </>
      )}

      {loading ? (
        <p className="muted">Loading...</p>
      ) : dues.length === 0 ? (
        <div className="empty-state">No bank dues recorded yet.</div>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>Business Unit</th>
              <th>Division</th>
              <th>Bank</th>
              <th>Account</th>
              <th>Due Date</th>
              <th>Facility</th>
              <th className="numeric">Amount</th>
              <th>Status</th>
              {canWrite && <th></th>}
            </tr>
          </thead>
          <tbody>
            {dues.map((d) => (
              <tr key={d.id}>
                <td>{d.business_unit_name}</td>
                <td>{d.division_name}</td>
                <td>{d.bank_short_name}</td>
                <td>{d.account_number}</td>
                <td>{d.due_date}</td>
                <td>{d.facility_type}</td>
                <td className="numeric">{formatSDG(d.amount)}</td>
                <td>
                  <span className={"badge " + (d.status === "Active" ? "badge--negative" : "badge--neutral")}>
                    {d.status}
                  </span>
                </td>
                {canWrite && (
                  <td>
                    {d.status === "Active" && (
                      <button className="btn btn--ghost" onClick={() => settle(d.id)}>
                        Mark Settled
                      </button>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function ReceivablesSection() {
  const { canWrite } = useAuth();
  const [editing, setEditing] = useState(false);
  const [rows, setRows] = useState<ReceivableFormRow[]>([]);
  const [amounts, setAmounts] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);

  async function startUpdate() {
    setLoading(true);
    setSaved(null);
    try {
      const res = await api.get<ReceivableFormRow[]>("/api/receivables/form");
      setRows(res.data);
      const initial: Record<number, string> = {};
      res.data.forEach((r) => (initial[r.account_id] = r.default_amount));
      setAmounts(initial);
      setEditing(true);
    } finally {
      setLoading(false);
    }
  }

  async function save() {
    setSaving(true);
    try {
      const today = new Date().toISOString().slice(0, 10);
      await api.post("/api/receivables/save", {
        position_date: today,
        rows: rows.map((r) => ({ account_id: r.account_id, amount: amounts[r.account_id] || "0" })),
      });
      setSaved(`Saved as today's (${today}) receivables position.`);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="card">
      <h2 className="section-title">Today's Receivables</h2>
      <p className="muted" style={{ marginTop: 0 }}>
        This feeds the Home page's coverage comparison. Start an update to see every account
        prefilled with its last recorded amount, adjust what's changed, and save.
      </p>
      {saved && <div className="alert alert--positive">{saved}</div>}
      {!editing && canWrite && (
        <button className="btn btn--primary" onClick={startUpdate} disabled={loading}>
          {loading ? "Loading..." : "Start Update"}
        </button>
      )}
      {editing && (
        <>
          {rows.length === 0 ? (
            <div className="empty-state">No accounts registered yet.</div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Business Unit</th>
                  <th>Division</th>
                  <th>Bank</th>
                  <th>Account</th>
                  <th>Currency</th>
                  <th className="numeric">Last Recorded</th>
                  <th className="numeric">Today's Amount</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.account_id}>
                    <td>{r.business_unit_name}</td>
                    <td>{r.division_name}</td>
                    <td>{r.bank_short_name}</td>
                    <td>
                      {r.account_name} ({r.account_number})
                    </td>
                    <td>{r.currency}</td>
                    <td className="numeric">
                      {formatSDG(r.default_amount)}
                      {r.default_amount_date ? ` (${r.default_amount_date})` : ""}
                    </td>
                    <td className="numeric">
                      <NumericFormat
                        style={{ textAlign: "right" }}
                        thousandSeparator=","
                        decimalScale={2}
                        allowNegative={false}
                        inputMode="decimal"
                        value={amounts[r.account_id] ?? ""}
                        onValueChange={(v) =>
                          setAmounts((prev) => ({ ...prev, [r.account_id]: v.value }))
                        }
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <div style={{ marginTop: "1rem", display: "flex", gap: "0.75rem" }}>
            <button className="btn btn--primary" onClick={save} disabled={saving || rows.length === 0}>
              {saving ? "Saving..." : "Save"}
            </button>
            <button className="btn btn--ghost" onClick={() => setEditing(false)} disabled={saving}>
              Cancel
            </button>
          </div>
        </>
      )}
    </div>
  );
}

export function BankDues() {
  return (
    <div className="page">
      <div className="page__header">
        <h1 className="page__title">Bank Dues &amp; Receivables</h1>
        <p className="page__subtitle">
          Register what's owed to banks and keep today's receivables position current.
        </p>
      </div>
      <DuesSection />
      <ReceivablesSection />
    </div>
  );
}
