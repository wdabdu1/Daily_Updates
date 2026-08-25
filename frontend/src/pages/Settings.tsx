import { useState } from "react";
import { api } from "../api/client";

export function Settings() {
  const [scope, setScope] = useState<"transactions" | "everything">("transactions");
  const [confirmText, setConfirmText] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function runReset() {
    setBusy(true);
    setResult(null);
    setError(null);
    try {
      const res = await api.post("/api/admin/reset-data", { scope, confirm: true });
      const deleted = res.data.deleted as Record<string, number>;
      const summary = Object.entries(deleted)
        .map(([k, v]) => `${v} ${k.replace(/_/g, " ")}`)
        .join(", ");
      setResult(`Cleared: ${summary}.`);
      setConfirmText("");
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Reset failed.");
    } finally {
      setBusy(false);
    }
  }

  const canConfirm = confirmText.trim().toUpperCase() === "WIPE";

  return (
    <div className="page">
      <div className="page__header">
        <h1 className="page__title">Settings</h1>
        <p className="page__subtitle">
          Business Units, Divisions, Banks, Currencies and User management are coming in a
          later phase. Data reset is available now.
        </p>
      </div>

      <div className="card">
        <p className="muted">
          Business Unit, Division, Bank, Currency and Master Account management currently
          happen implicitly through the Excel imports on the FX Rates and Bank Dues pages
          (unknown ones are created automatically from your upload). A dedicated management UI
          for these, plus User management, lands here in a later phase.
        </p>
      </div>

      <div className="card" style={{ borderColor: "var(--color-negative)" }}>
        <h2 className="section-title" style={{ color: "var(--color-negative)" }}>
          Danger Zone: Reset Data
        </h2>
        <p className="muted">
          Use this to clear out test data before loading final figures. This cannot be undone.
        </p>
        <div className="form-grid" style={{ maxWidth: 480 }}>
          <div>
            <label className="field-label">Scope</label>
            <select value={scope} onChange={(e) => setScope(e.target.value as any)}>
              <option value="transactions">
                Transactions only (Bank Dues, Receivables, FX Rates)
              </option>
              <option value="everything">
                Everything (also Business Units, Divisions, Banks, Master Accounts)
              </option>
            </select>
          </div>
          <div>
            <label className="field-label">Type WIPE to confirm</label>
            <input value={confirmText} onChange={(e) => setConfirmText(e.target.value)} />
          </div>
        </div>
        {error && <p className="error-text">{error}</p>}
        {result && <div className="alert alert--positive" style={{ marginTop: "1rem" }}>{result}</div>}
        <button
          className="btn btn--primary"
          style={{ marginTop: "1rem", background: "var(--color-negative)" }}
          disabled={!canConfirm || busy}
          onClick={runReset}
        >
          {busy ? "Clearing..." : "Clear Data"}
        </button>
      </div>
    </div>
  );
}
