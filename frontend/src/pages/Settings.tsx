import { useEffect, useState } from "react";
import { api, downloadXlsx, errMsg } from "../api/client";
import { useAuth } from "../auth/AuthContext";

interface BusinessUnit {
  id: number;
  name: string;
}
interface Division {
  id: number;
  name: string;
  business_unit_id: number;
}
interface Bank {
  id: number;
  short_name: string;
  full_name: string;
}
interface Currency {
  code: string;
}
interface CurrencyPair {
  id: number;
  base_currency: string;
  quote_currency: string;
  supports_extended_rates: boolean;
  is_default: boolean;
}
interface AppUser {
  id: number;
  username: string;
  role: string;
  display_name: string | null;
  email: string | null;
}
interface Account {
  id: number;
  business_unit_id: number | null;
  division_id: number | null;
  bank_id: number;
  account_name: string;
  account_number: string;
  currency: string;
  business_unit_name: string | null;
  division_name: string | null;
  bank_short_name: string | null;
}

// ---------------------------------------------------------------- Business Units
function BusinessUnitsSection({ onChange }: { onChange: () => void }) {
  const [items, setItems] = useState<BusinessUnit[]>([]);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");

  function refresh() {
    api.get<BusinessUnit[]>("/api/settings/business-units").then((res) => setItems(res.data));
  }
  useEffect(refresh, []);

  async function add() {
    if (!name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api.post("/api/settings/business-units", { name: name.trim() });
      setName("");
      refresh();
      onChange();
    } catch (e: any) {
      setError(errMsg(e, "Couldn't add this business unit."));
    } finally {
      setBusy(false);
    }
  }

  function startEdit(b: BusinessUnit) {
    setEditingId(b.id);
    setEditName(b.name);
    setError(null);
  }

  async function saveEdit(id: number) {
    if (!editName.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api.put(`/api/settings/business-units/${id}`, { name: editName.trim() });
      setEditingId(null);
      refresh();
      onChange();
    } catch (e: any) {
      setError(errMsg(e, "Couldn't update this business unit."));
    } finally {
      setBusy(false);
    }
  }

  async function remove(b: BusinessUnit) {
    if (!window.confirm(`Delete business unit "${b.name}"?`)) return;
    setError(null);
    try {
      await api.delete(`/api/settings/business-units/${b.id}`);
      refresh();
      onChange();
    } catch (e: any) {
      setError(errMsg(e, "Couldn't delete this business unit."));
    }
  }

  return (
    <div className="card">
      <h2 className="section-title">Business Units</h2>
      <table className="data-table">
        <thead>
          <tr>
            <th>Name</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {items.map((b) =>
            editingId === b.id ? (
              <tr key={b.id}>
                <td>
                  <input value={editName} onChange={(e) => setEditName(e.target.value)} />
                </td>
                <td>
                  <div className="row-actions">
                    <button className="btn btn--small" onClick={() => saveEdit(b.id)} disabled={busy}>
                      Save
                    </button>
                    <button className="btn btn--small" onClick={() => setEditingId(null)} disabled={busy}>
                      Cancel
                    </button>
                  </div>
                </td>
              </tr>
            ) : (
              <tr key={b.id}>
                <td>{b.name}</td>
                <td>
                  <div className="row-actions">
                    <button className="btn btn--ghost btn--small" onClick={() => startEdit(b)}>
                      Edit
                    </button>
                    <button className="btn btn--danger btn--small" onClick={() => remove(b)}>
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
            )
          )}
          {items.length === 0 && (
            <tr>
              <td className="muted" colSpan={2}>
                No business units yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>
      <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem", alignItems: "flex-end" }}>
        <div style={{ flex: 1 }}>
          <label className="field-label">New business unit name</label>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Corporate Treasury" />
        </div>
        <button className="btn btn--primary" disabled={!name.trim() || busy} onClick={add}>
          {busy ? "Adding..." : "Add"}
        </button>
      </div>
      {error && <p className="error-text">{error}</p>}
    </div>
  );
}

// ------------------------------------------------------------------- Divisions
function DivisionsSection({
  businessUnits,
  onChange,
}: {
  businessUnits: BusinessUnit[];
  onChange: () => void;
}) {
  const [items, setItems] = useState<Division[]>([]);
  const [name, setName] = useState("");
  const [buId, setBuId] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editBuId, setEditBuId] = useState<string>("");

  function refresh() {
    api.get<Division[]>("/api/settings/divisions").then((res) => setItems(res.data));
  }
  useEffect(refresh, []);
  useEffect(() => {
    if (!buId && businessUnits.length > 0) setBuId(String(businessUnits[0].id));
  }, [businessUnits, buId]);

  async function add() {
    if (!name.trim() || !buId) return;
    setBusy(true);
    setError(null);
    try {
      await api.post("/api/settings/divisions", { name: name.trim(), business_unit_id: Number(buId) });
      setName("");
      refresh();
      onChange();
    } catch (e: any) {
      setError(errMsg(e, "Couldn't add this division."));
    } finally {
      setBusy(false);
    }
  }

  function startEdit(d: Division) {
    setEditingId(d.id);
    setEditName(d.name);
    setEditBuId(String(d.business_unit_id));
    setError(null);
  }

  async function saveEdit(id: number) {
    if (!editName.trim() || !editBuId) return;
    setBusy(true);
    setError(null);
    try {
      await api.put(`/api/settings/divisions/${id}`, {
        name: editName.trim(),
        business_unit_id: Number(editBuId),
      });
      setEditingId(null);
      refresh();
      onChange();
    } catch (e: any) {
      setError(errMsg(e, "Couldn't update this division."));
    } finally {
      setBusy(false);
    }
  }

  async function remove(d: Division) {
    if (!window.confirm(`Delete division "${d.name}"?`)) return;
    setError(null);
    try {
      await api.delete(`/api/settings/divisions/${d.id}`);
      refresh();
      onChange();
    } catch (e: any) {
      setError(errMsg(e, "Couldn't delete this division."));
    }
  }

  const buName = (id: number) => businessUnits.find((b) => b.id === id)?.name || `#${id}`;

  return (
    <div className="card">
      <h2 className="section-title">Divisions</h2>
      <table className="data-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Business Unit</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {items.map((d) =>
            editingId === d.id ? (
              <tr key={d.id}>
                <td>
                  <input value={editName} onChange={(e) => setEditName(e.target.value)} />
                </td>
                <td>
                  <select value={editBuId} onChange={(e) => setEditBuId(e.target.value)}>
                    {businessUnits.map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.name}
                      </option>
                    ))}
                  </select>
                </td>
                <td>
                  <div className="row-actions">
                    <button className="btn btn--small" onClick={() => saveEdit(d.id)} disabled={busy}>
                      Save
                    </button>
                    <button className="btn btn--small" onClick={() => setEditingId(null)} disabled={busy}>
                      Cancel
                    </button>
                  </div>
                </td>
              </tr>
            ) : (
              <tr key={d.id}>
                <td>{d.name}</td>
                <td>{buName(d.business_unit_id)}</td>
                <td>
                  <div className="row-actions">
                    <button className="btn btn--ghost btn--small" onClick={() => startEdit(d)}>
                      Edit
                    </button>
                    <button className="btn btn--danger btn--small" onClick={() => remove(d)}>
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
            )
          )}
          {items.length === 0 && (
            <tr>
              <td className="muted" colSpan={3}>
                No divisions yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>
      <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem", alignItems: "flex-end" }}>
        <div>
          <label className="field-label">Business Unit</label>
          <select value={buId} onChange={(e) => setBuId(e.target.value)}>
            {businessUnits.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </select>
        </div>
        <div style={{ flex: 1 }}>
          <label className="field-label">New division name</label>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Operations" />
        </div>
        <button className="btn btn--primary" disabled={!name.trim() || !buId || busy} onClick={add}>
          {busy ? "Adding..." : "Add"}
        </button>
      </div>
      {businessUnits.length === 0 && (
        <p className="muted" style={{ marginTop: "0.5rem" }}>
          Add a Business Unit above first.
        </p>
      )}
      {error && <p className="error-text">{error}</p>}
    </div>
  );
}

// ----------------------------------------------------------------------- Banks
function BanksSection({ onChange }: { onChange: () => void }) {
  const [items, setItems] = useState<Bank[]>([]);
  const [shortName, setShortName] = useState("");
  const [fullName, setFullName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editShort, setEditShort] = useState("");
  const [editFull, setEditFull] = useState("");

  function refresh() {
    api.get<Bank[]>("/api/settings/banks").then((res) => setItems(res.data));
  }
  useEffect(refresh, []);

  async function add() {
    if (!shortName.trim() || !fullName.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api.post("/api/settings/banks", { short_name: shortName.trim(), full_name: fullName.trim() });
      setShortName("");
      setFullName("");
      refresh();
      onChange();
    } catch (e: any) {
      setError(errMsg(e, "Couldn't add this bank."));
    } finally {
      setBusy(false);
    }
  }

  function startEdit(b: Bank) {
    setEditingId(b.id);
    setEditShort(b.short_name);
    setEditFull(b.full_name);
    setError(null);
  }

  async function saveEdit(id: number) {
    if (!editShort.trim() || !editFull.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api.put(`/api/settings/banks/${id}`, {
        short_name: editShort.trim(),
        full_name: editFull.trim(),
      });
      setEditingId(null);
      refresh();
      onChange();
    } catch (e: any) {
      setError(errMsg(e, "Couldn't update this bank."));
    } finally {
      setBusy(false);
    }
  }

  async function remove(b: Bank) {
    if (!window.confirm(`Delete bank "${b.short_name}"?`)) return;
    setError(null);
    try {
      await api.delete(`/api/settings/banks/${b.id}`);
      refresh();
      onChange();
    } catch (e: any) {
      setError(errMsg(e, "Couldn't delete this bank."));
    }
  }

  return (
    <div className="card">
      <h2 className="section-title">Banks</h2>
      <table className="data-table">
        <thead>
          <tr>
            <th>Short Name</th>
            <th>Full Name</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {items.map((b) =>
            editingId === b.id ? (
              <tr key={b.id}>
                <td>
                  <input value={editShort} onChange={(e) => setEditShort(e.target.value)} />
                </td>
                <td>
                  <input value={editFull} onChange={(e) => setEditFull(e.target.value)} />
                </td>
                <td>
                  <div className="row-actions">
                    <button className="btn btn--small" onClick={() => saveEdit(b.id)} disabled={busy}>
                      Save
                    </button>
                    <button className="btn btn--small" onClick={() => setEditingId(null)} disabled={busy}>
                      Cancel
                    </button>
                  </div>
                </td>
              </tr>
            ) : (
              <tr key={b.id}>
                <td>{b.short_name}</td>
                <td>{b.full_name}</td>
                <td>
                  <div className="row-actions">
                    <button className="btn btn--ghost btn--small" onClick={() => startEdit(b)}>
                      Edit
                    </button>
                    <button className="btn btn--danger btn--small" onClick={() => remove(b)}>
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
            )
          )}
          {items.length === 0 && (
            <tr>
              <td className="muted" colSpan={3}>
                No banks yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>
      <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem", alignItems: "flex-end" }}>
        <div>
          <label className="field-label">Short name</label>
          <input value={shortName} onChange={(e) => setShortName(e.target.value)} placeholder="e.g. CIB" />
        </div>
        <div style={{ flex: 1 }}>
          <label className="field-label">Full name</label>
          <input
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            placeholder="e.g. Commercial International Bank"
          />
        </div>
        <button className="btn btn--primary" disabled={!shortName.trim() || !fullName.trim() || busy} onClick={add}>
          {busy ? "Adding..." : "Add"}
        </button>
      </div>
      {error && <p className="error-text">{error}</p>}
    </div>
  );
}

// ------------------------------------------------------------------ Currencies
function CurrenciesSection({ onChange }: { onChange: () => void }) {
  const [items, setItems] = useState<Currency[]>([]);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function refresh() {
    api.get<Currency[]>("/api/settings/currencies").then((res) => setItems(res.data));
  }
  useEffect(refresh, []);

  async function add() {
    if (!code.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api.post("/api/settings/currencies", { code: code.trim().toUpperCase() });
      setCode("");
      refresh();
      onChange();
    } catch (e: any) {
      setError(errMsg(e, "Couldn't add this currency."));
    } finally {
      setBusy(false);
    }
  }

  async function remove(c: Currency) {
    if (!window.confirm(`Delete currency "${c.code}"?`)) return;
    setError(null);
    try {
      await api.delete(`/api/settings/currencies/${c.code}`);
      refresh();
      onChange();
    } catch (e: any) {
      setError(errMsg(e, "Couldn't delete this currency."));
    }
  }

  return (
    <div className="card">
      <h2 className="section-title">Currencies</h2>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginBottom: "1rem" }}>
        {items.map((c) => (
          <span key={c.code} className="badge" style={{ paddingRight: "0.4rem" }}>
            {c.code}
            <button
              onClick={() => remove(c)}
              title={`Delete ${c.code}`}
              style={{
                border: "none",
                background: "transparent",
                cursor: "pointer",
                color: "inherit",
                fontWeight: 700,
                padding: 0,
                marginLeft: "0.15rem",
                lineHeight: 1,
              }}
            >
              &times;
            </button>
          </span>
        ))}
        {items.length === 0 && <span className="muted">No currencies yet.</span>}
      </div>
      <div style={{ display: "flex", gap: "0.5rem", alignItems: "flex-end" }}>
        <div>
          <label className="field-label">New currency code</label>
          <input
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            placeholder="e.g. EUR"
            maxLength={10}
            style={{ width: 120 }}
          />
        </div>
        <button className="btn btn--primary" disabled={!code.trim() || busy} onClick={add}>
          {busy ? "Adding..." : "Add"}
        </button>
      </div>
      {error && <p className="error-text">{error}</p>}
    </div>
  );
}

// -------------------------------------------------------------- Currency Pairs
function CurrencyPairsSection({ currencies, onChange }: { currencies: Currency[]; onChange: () => void }) {
  const [items, setItems] = useState<CurrencyPair[]>([]);
  const [base, setBase] = useState("");
  const [quote, setQuote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function refresh() {
    api.get<CurrencyPair[]>("/api/settings/currency-pairs").then((res) => setItems(res.data));
  }
  useEffect(refresh, []);
  useEffect(() => {
    if (currencies.length > 0) {
      if (!base) setBase(currencies[0].code);
      if (!quote) setQuote(currencies.find((c) => c.code === "SDG")?.code || currencies[0].code);
    }
  }, [currencies, base, quote]);

  async function add() {
    if (!base || !quote || base === quote) return;
    setBusy(true);
    setError(null);
    try {
      await api.post("/api/settings/currency-pairs", { base_currency: base, quote_currency: quote });
      refresh();
      onChange();
    } catch (e: any) {
      setError(errMsg(e, "Couldn't add this currency pair."));
    } finally {
      setBusy(false);
    }
  }

  async function remove(p: CurrencyPair) {
    if (!window.confirm(`Delete currency pair ${p.base_currency}/${p.quote_currency}?`)) return;
    setError(null);
    try {
      await api.delete(`/api/settings/currency-pairs/${p.id}`);
      refresh();
      onChange();
    } catch (e: any) {
      setError(errMsg(e, "Couldn't delete this currency pair."));
    }
  }

  return (
    <div className="card">
      <h2 className="section-title">Currency Pairs</h2>
      <p className="muted" style={{ marginTop: 0 }}>
        A pair involving SDG automatically gets CBOS and Pricing rate types in addition to Market;
        any other pair only tracks a Market Rate.
      </p>
      <table className="data-table">
        <thead>
          <tr>
            <th>Pair</th>
            <th>Rate types</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {items.map((p) => (
            <tr key={p.id}>
              <td>
                {p.base_currency}/{p.quote_currency}
                {p.is_default ? " (default)" : ""}
              </td>
              <td>{p.supports_extended_rates ? "Market, CBOS, Pricing" : "Market"}</td>
              <td>
                <button className="btn btn--danger btn--small" onClick={() => remove(p)}>
                  Delete
                </button>
              </td>
            </tr>
          ))}
          {items.length === 0 && (
            <tr>
              <td className="muted" colSpan={3}>
                No currency pairs yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>
      <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem", alignItems: "flex-end" }}>
        <div>
          <label className="field-label">Base</label>
          <select value={base} onChange={(e) => setBase(e.target.value)}>
            {currencies.map((c) => (
              <option key={c.code} value={c.code}>
                {c.code}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="field-label">Quote</label>
          <select value={quote} onChange={(e) => setQuote(e.target.value)}>
            {currencies.map((c) => (
              <option key={c.code} value={c.code}>
                {c.code}
              </option>
            ))}
          </select>
        </div>
        <button className="btn btn--primary" disabled={!base || !quote || base === quote || busy} onClick={add}>
          {busy ? "Adding..." : "Add pair"}
        </button>
      </div>
      {currencies.length === 0 && (
        <p className="muted" style={{ marginTop: "0.5rem" }}>
          Add a Currency above first.
        </p>
      )}
      {error && <p className="error-text">{error}</p>}
    </div>
  );
}

// Round 12 removed this UI (One-Time Historical Import + Import Rates from
// Excel) in favor of curl, since the endpoints stayed reachable directly.
// Round 17 brings the historical importer back at the user's request: this
// session's cloud sandbox can only ever build and test against a private
// throwaway database here, never the user's live Railway deployment, so
// getting real data onto the live dashboard always requires an action the
// user takes themselves -- and curl isn't a comfortable tool for that on
// an ongoing basis. The generic long-format importer (/api/fx/import) and
// the Bank Dues importer stay curl-only for now; only the "wide" one-row-
// per-day historical layout (the one the user's actual currency-history
// file uses) gets a UI again.
function FxHistoryImportSection() {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{
    imported: number;
    updated: number;
    skipped: { row_number: number; reason: string }[];
  } | null>(null);

  async function upload() {
    if (!file) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await api.post("/api/fx/import-history", formData);
      setResult(res.data);
      setFile(null);
    } catch (e: any) {
      setError(errMsg(e, "Import failed."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h2 className="section-title">Currency History Import</h2>
      <p className="muted" style={{ marginTop: 0 }}>
        One-time bulk load for the FX Rates page's Market/CBOS/Pricing history -- a "wide"
        spreadsheet with one row per calendar day and separate Market/CBOS/Pricing x USD/Euro/AED
        columns (not the same layout as any other import in this app -- download the template
        below to see the exact columns expected). Re-uploading a date that's already on file
        updates it instead of creating a duplicate, so it's safe to re-run after fixing a mistake.
        Any of the 9 rate columns can be left blank for a date where that particular rate type
        wasn't recorded yet -- e.g. Pricing only existing from a certain date onward is expected,
        not an error.
      </p>
      <div style={{ display: "flex", gap: "0.75rem", alignItems: "center", flexWrap: "wrap" }}>
        <button
          className="btn btn--ghost"
          onClick={() => downloadXlsx("/api/fx/import-history/template", "fx_history_import_template.xlsx")}
        >
          Download Template
        </button>
        <input
          type="file"
          accept=".xlsx"
          onChange={(e) => {
            setFile(e.target.files?.[0] ?? null);
            setResult(null);
            setError(null);
          }}
        />
        <button className="btn btn--primary" disabled={!file || busy} onClick={upload}>
          {busy ? "Uploading..." : "Upload"}
        </button>
      </div>
      {error && <p className="error-text">{error}</p>}
      {result && (
        <div style={{ marginTop: "0.75rem" }}>
          <p className="muted">
            Imported {result.imported}, updated {result.updated}
            {result.skipped.length > 0 ? `, skipped ${result.skipped.length}.` : "."}
          </p>
          {result.skipped.length > 0 && (
            <ul style={{ maxHeight: 220, overflowY: "auto", fontSize: "0.82rem" }}>
              {result.skipped.slice(0, 30).map((s, i) => (
                <li key={i}>
                  Row {s.row_number}: {s.reason}
                </li>
              ))}
              {result.skipped.length > 30 && <li>...and {result.skipped.length - 30} more.</li>}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------- Accounts
interface AccountDraft {
  business_unit_id: string;
  division_id: string;
  bank_id: string;
  account_name: string;
  account_number: string;
  currency: string;
}

// Hoisted to module scope deliberately -- this used to be defined INSIDE
// AccountsSection's render body, which meant React saw a brand-new
// component function on every keystroke (since typing updates `draft`/
// `editDraft` state, which re-renders AccountsSection, which used to
// redefine this function again). A new function identity at the same tree
// position makes React treat it as a different component type and
// remount the whole subtree -- including the text inputs -- which is
// exactly what dropped focus after every single character typed into
// Account Name. Defining it once, up here, keeps its identity stable
// across re-renders so the inputs stay mounted and keep focus.
function AccountDraftFields({
  value,
  onChange,
  businessUnits,
  divisions,
  banks,
  currencies,
}: {
  value: AccountDraft;
  onChange: (v: AccountDraft) => void;
  businessUnits: BusinessUnit[];
  divisions: Division[];
  banks: Bank[];
  currencies: Currency[];
}) {
  const divisionsFor = (buId: string) =>
    buId ? divisions.filter((d) => d.business_unit_id === Number(buId)) : [];

  return (
    <>
      <div>
        <label className="field-label">Business Unit</label>
        <select
          value={value.business_unit_id}
          onChange={(e) => onChange({ ...value, business_unit_id: e.target.value, division_id: "" })}
        >
          <option value="">— none —</option>
          {businessUnits.map((b) => (
            <option key={b.id} value={b.id}>
              {b.name}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label className="field-label">Division</label>
        <select
          value={value.division_id}
          onChange={(e) => onChange({ ...value, division_id: e.target.value })}
          disabled={!value.business_unit_id}
        >
          <option value="">— none —</option>
          {divisionsFor(value.business_unit_id).map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label className="field-label">Bank</label>
        <select value={value.bank_id} onChange={(e) => onChange({ ...value, bank_id: e.target.value })}>
          {banks.map((b) => (
            <option key={b.id} value={b.id}>
              {b.short_name}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label className="field-label">Account Name</label>
        <input
          value={value.account_name}
          onChange={(e) => onChange({ ...value, account_name: e.target.value })}
          placeholder="e.g. Treasury Main AED"
        />
      </div>
      <div>
        <label className="field-label">Account Number</label>
        <input
          value={value.account_number}
          onChange={(e) => onChange({ ...value, account_number: e.target.value })}
          placeholder="e.g. 1001-AED"
        />
      </div>
      <div>
        <label className="field-label">Currency</label>
        <select value={value.currency} onChange={(e) => onChange({ ...value, currency: e.target.value })}>
          {currencies.map((c) => (
            <option key={c.code} value={c.code}>
              {c.code}
            </option>
          ))}
        </select>
      </div>
    </>
  );
}

function AccountsSection({
  businessUnits,
  divisions,
  banks,
  currencies,
}: {
  businessUnits: BusinessUnit[];
  divisions: Division[];
  banks: Bank[];
  currencies: Currency[];
}) {
  const emptyDraft = {
    business_unit_id: "" as string,
    division_id: "" as string,
    bank_id: "" as string,
    account_name: "",
    account_number: "",
    currency: "",
  };
  const [items, setItems] = useState<Account[]>([]);
  const [draft, setDraft] = useState(emptyDraft);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editDraft, setEditDraft] = useState(emptyDraft);

  function refresh() {
    api.get<Account[]>("/api/accounts").then((res) => setItems(res.data));
  }
  useEffect(refresh, []);
  useEffect(() => {
    if (!draft.bank_id && banks.length > 0) setDraft((d) => ({ ...d, bank_id: String(banks[0].id) }));
    if (!draft.currency && currencies.length > 0)
      setDraft((d) => ({ ...d, currency: currencies.find((c) => c.code === "SDG")?.code || currencies[0].code }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [banks, currencies]);

  function toPayload(d: typeof emptyDraft) {
    return {
      business_unit_id: d.business_unit_id ? Number(d.business_unit_id) : null,
      division_id: d.division_id ? Number(d.division_id) : null,
      bank_id: Number(d.bank_id),
      account_name: d.account_name.trim(),
      account_number: d.account_number.trim(),
      currency: d.currency,
    };
  }

  async function add() {
    if (!draft.bank_id || !draft.account_name.trim() || !draft.account_number.trim() || !draft.currency) return;
    setBusy(true);
    setError(null);
    try {
      await api.post("/api/accounts", toPayload(draft));
      setDraft({ ...emptyDraft, bank_id: draft.bank_id, currency: draft.currency });
      refresh();
    } catch (e: any) {
      setError(errMsg(e, "Couldn't add this account."));
    } finally {
      setBusy(false);
    }
  }

  function startEdit(a: Account) {
    setEditingId(a.id);
    setEditDraft({
      business_unit_id: a.business_unit_id ? String(a.business_unit_id) : "",
      division_id: a.division_id ? String(a.division_id) : "",
      bank_id: String(a.bank_id),
      account_name: a.account_name,
      account_number: a.account_number,
      currency: a.currency,
    });
    setError(null);
  }

  async function saveEdit(id: number) {
    if (!editDraft.bank_id || !editDraft.account_name.trim() || !editDraft.account_number.trim() || !editDraft.currency)
      return;
    setBusy(true);
    setError(null);
    try {
      await api.put(`/api/accounts/${id}`, toPayload(editDraft));
      setEditingId(null);
      refresh();
    } catch (e: any) {
      setError(errMsg(e, "Couldn't update this account."));
    } finally {
      setBusy(false);
    }
  }

  async function remove(a: Account) {
    if (!window.confirm(`Delete account "${a.account_name}" (${a.account_number})?`)) return;
    setError(null);
    try {
      await api.delete(`/api/accounts/${a.id}`);
      refresh();
    } catch (e: any) {
      setError(errMsg(e, "Couldn't delete this account."));
    }
  }

  return (
    <div className="card">
      <h2 className="section-title">Accounts</h2>
      <p className="muted" style={{ marginTop: 0 }}>
        Master accounts also get created automatically from a Bank Dues import -- use this to add
        one directly, or to fix a typo/reassign one without re-uploading. Business Unit and
        Division are optional (see Round 5 notes) if you don't have that attribution yet.
      </p>
      <table className="data-table">
        <thead>
          <tr>
            <th>Business Unit</th>
            <th>Division</th>
            <th>Bank</th>
            <th>Account Name</th>
            <th>Account Number</th>
            <th>Currency</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {items.map((a) =>
            editingId === a.id ? (
              <tr key={a.id}>
                <td colSpan={6}>
                  <div className="form-grid">
                    <AccountDraftFields
                      value={editDraft}
                      onChange={setEditDraft}
                      businessUnits={businessUnits}
                      divisions={divisions}
                      banks={banks}
                      currencies={currencies}
                    />
                  </div>
                </td>
                <td>
                  <div className="row-actions">
                    <button className="btn btn--small" onClick={() => saveEdit(a.id)} disabled={busy}>
                      Save
                    </button>
                    <button className="btn btn--small" onClick={() => setEditingId(null)} disabled={busy}>
                      Cancel
                    </button>
                  </div>
                </td>
              </tr>
            ) : (
              <tr key={a.id}>
                <td>{a.business_unit_name || "Unassigned"}</td>
                <td>{a.division_name || "—"}</td>
                <td>{a.bank_short_name}</td>
                <td>{a.account_name}</td>
                <td>{a.account_number}</td>
                <td>{a.currency}</td>
                <td>
                  <div className="row-actions">
                    <button className="btn btn--ghost btn--small" onClick={() => startEdit(a)}>
                      Edit
                    </button>
                    <button className="btn btn--danger btn--small" onClick={() => remove(a)}>
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
            )
          )}
          {items.length === 0 && (
            <tr>
              <td className="muted" colSpan={7}>
                No accounts yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>
      <div className="form-grid" style={{ marginTop: "1rem" }}>
        <AccountDraftFields
          value={draft}
          onChange={setDraft}
          businessUnits={businessUnits}
          divisions={divisions}
          banks={banks}
          currencies={currencies}
        />
      </div>
      <button
        className="btn btn--primary"
        style={{ marginTop: "0.75rem" }}
        disabled={!draft.bank_id || !draft.account_name.trim() || !draft.account_number.trim() || !draft.currency || busy}
        onClick={add}
      >
        {busy ? "Adding..." : "Add account"}
      </button>
      {banks.length === 0 && (
        <p className="muted" style={{ marginTop: "0.5rem" }}>
          Add a Bank above first.
        </p>
      )}
      {error && <p className="error-text">{error}</p>}
    </div>
  );
}

// ----------------------------------------------------------------------- Users
function UsersSection() {
  const { username: myUsername } = useAuth();
  const [items, setItems] = useState<AppUser[]>([]);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("ReadWrite");
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resetting, setResetting] = useState<number | null>(null);
  const [resetPw, setResetPw] = useState("");
  const [resetMsg, setResetMsg] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editUsername, setEditUsername] = useState("");
  const [editRole, setEditRole] = useState("ReadWrite");
  const [editDisplayName, setEditDisplayName] = useState("");
  const [editEmail, setEditEmail] = useState("");

  function refresh() {
    api.get<AppUser[]>("/api/settings/users").then((res) => setItems(res.data));
  }
  useEffect(refresh, []);

  async function add() {
    if (!username.trim() || !password) return;
    setBusy(true);
    setError(null);
    try {
      await api.post("/api/settings/users", {
        username: username.trim(),
        password,
        role,
        display_name: displayName.trim() || null,
        email: email.trim() || null,
      });
      setUsername("");
      setPassword("");
      setRole("ReadWrite");
      setDisplayName("");
      setEmail("");
      refresh();
    } catch (e: any) {
      setError(errMsg(e, "Couldn't add this user."));
    } finally {
      setBusy(false);
    }
  }

  async function doReset(id: number) {
    if (!resetPw) return;
    setResetMsg(null);
    try {
      await api.post(`/api/settings/users/${id}/reset-password`, { username: "-", password: resetPw, role: "-" });
      setResetMsg("Password updated.");
      setResetting(null);
      setResetPw("");
    } catch (e: any) {
      setResetMsg(errMsg(e, "Couldn't reset this password."));
    }
  }

  function startEdit(u: AppUser) {
    setEditingId(u.id);
    setEditUsername(u.username);
    setEditRole(u.role);
    setEditDisplayName(u.display_name || "");
    setEditEmail(u.email || "");
    setError(null);
  }

  async function saveEdit(id: number) {
    if (!editUsername.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api.put(`/api/settings/users/${id}`, {
        username: editUsername.trim(),
        role: editRole,
        display_name: editDisplayName.trim() || null,
        email: editEmail.trim() || null,
      });
      setEditingId(null);
      refresh();
    } catch (e: any) {
      setError(errMsg(e, "Couldn't update this user."));
    } finally {
      setBusy(false);
    }
  }

  async function remove(u: AppUser) {
    if (!window.confirm(`Delete user "${u.username}"?`)) return;
    setError(null);
    try {
      await api.delete(`/api/settings/users/${u.id}`);
      refresh();
    } catch (e: any) {
      setError(errMsg(e, "Couldn't delete this user."));
    }
  }

  return (
    <div className="card">
      <h2 className="section-title">Users</h2>
      <p className="muted" style={{ marginTop: 0 }}>
        Everyone migrated from the old app currently shares the same bootstrap password. Reset
        each user's password here once they're set up.
      </p>
      <table className="data-table">
        <thead>
          <tr>
            <th>Username</th>
            <th>Display Name</th>
            <th>Email</th>
            <th>Role</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {items.map((u) => (
            <tr key={u.id}>
              {editingId === u.id ? (
                <>
                  <td>
                    <input value={editUsername} onChange={(e) => setEditUsername(e.target.value)} />
                  </td>
                  <td>
                    <input
                      value={editDisplayName}
                      onChange={(e) => setEditDisplayName(e.target.value)}
                      placeholder="(optional)"
                    />
                  </td>
                  <td>
                    <input
                      type="email"
                      value={editEmail}
                      onChange={(e) => setEditEmail(e.target.value)}
                      placeholder="(optional)"
                    />
                  </td>
                  <td>
                    <select value={editRole} onChange={(e) => setEditRole(e.target.value)}>
                      <option value="Manager">Manager</option>
                      <option value="ReadWrite">ReadWrite</option>
                      <option value="ReadOnly">ReadOnly</option>
                    </select>
                  </td>
                  <td>
                    <div className="row-actions">
                      <button className="btn btn--small" onClick={() => saveEdit(u.id)} disabled={busy}>
                        Save
                      </button>
                      <button className="btn btn--small" onClick={() => setEditingId(null)} disabled={busy}>
                        Cancel
                      </button>
                    </div>
                  </td>
                </>
              ) : (
                <>
                  <td>{u.username}</td>
                  <td>{u.display_name || <span className="muted">—</span>}</td>
                  <td>{u.email || <span className="muted">—</span>}</td>
                  <td>{u.role}</td>
                  <td>
                    {resetting === u.id ? (
                      <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                        <input
                          type="password"
                          placeholder="New password"
                          value={resetPw}
                          onChange={(e) => setResetPw(e.target.value)}
                          style={{ width: 160 }}
                        />
                        <button className="btn btn--small" onClick={() => doReset(u.id)} disabled={!resetPw}>
                          Save
                        </button>
                        <button
                          className="btn btn--small"
                          onClick={() => {
                            setResetting(null);
                            setResetPw("");
                          }}
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <div className="row-actions">
                        <button
                          className="btn btn--ghost btn--small"
                          onClick={() => {
                            setResetting(u.id);
                            setResetPw("");
                            setResetMsg(null);
                          }}
                        >
                          Reset password
                        </button>
                        <button className="btn btn--ghost btn--small" onClick={() => startEdit(u)}>
                          Edit
                        </button>
                        <button
                          className="btn btn--danger btn--small"
                          onClick={() => remove(u)}
                          disabled={u.username === myUsername}
                          title={u.username === myUsername ? "You can't delete your own account." : ""}
                        >
                          Delete
                        </button>
                      </div>
                    )}
                  </td>
                </>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      {resetMsg && <p className="muted">{resetMsg}</p>}
      <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem", alignItems: "flex-end", flexWrap: "wrap" }}>
        <div>
          <label className="field-label">Username</label>
          <input value={username} onChange={(e) => setUsername(e.target.value)} />
        </div>
        <div>
          <label className="field-label">Display Name</label>
          <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="(optional)" />
        </div>
        <div>
          <label className="field-label">Email</label>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="(optional)" />
        </div>
        <div>
          <label className="field-label">Password</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>
        <div>
          <label className="field-label">Role</label>
          <select value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="Manager">Manager</option>
            <option value="ReadWrite">ReadWrite</option>
            <option value="ReadOnly">ReadOnly</option>
          </select>
        </div>
        <button className="btn btn--primary" disabled={!username.trim() || !password || busy} onClick={add}>
          {busy ? "Adding..." : "Add user"}
        </button>
      </div>
      {error && <p className="error-text">{error}</p>}
    </div>
  );
}

// Round 12: the Danger Zone / Reset Data UI card removed from Settings at
// the user's request. POST /api/admin/reset-data is untouched in the
// backend (Manager-only, confirm=true required) -- still reachable
// directly, e.g. via curl. See the project doc for the exact call and the
// three scopes ("transactions" / "accounts" / "everything").

export function Settings() {
  const [businessUnits, setBusinessUnits] = useState<BusinessUnit[]>([]);
  const [divisions, setDivisions] = useState<Division[]>([]);
  const [banks, setBanks] = useState<Bank[]>([]);
  const [currencies, setCurrencies] = useState<Currency[]>([]);
  const [refreshKey, setRefreshKey] = useState(0);

  function refreshShared() {
    api.get<BusinessUnit[]>("/api/settings/business-units").then((res) => setBusinessUnits(res.data));
    api.get<Division[]>("/api/settings/divisions").then((res) => setDivisions(res.data));
    api.get<Bank[]>("/api/settings/banks").then((res) => setBanks(res.data));
    api.get<Currency[]>("/api/settings/currencies").then((res) => setCurrencies(res.data));
  }
  useEffect(refreshShared, [refreshKey]);

  const bump = () => setRefreshKey((k) => k + 1);

  return (
    <div className="page">
      <div className="page__header">
        <h1 className="page__title">Settings</h1>
        <p className="page__subtitle">
          Set up Business Units, Divisions, Banks and Currencies here so they're ready before you
          import Bank Dues or FX Rates -- the Excel imports still auto-create anything you leave
          out, but predefining them here avoids surprises and typos. Every entity below can now be
          edited or deleted; deleting is blocked (with a clear reason) if something still depends
          on it.
        </p>
      </div>

      <BusinessUnitsSection onChange={bump} />
      <DivisionsSection businessUnits={businessUnits} onChange={bump} />
      <BanksSection onChange={bump} />
      <CurrenciesSection onChange={bump} />
      <CurrencyPairsSection currencies={currencies} onChange={bump} />
      <FxHistoryImportSection />
      <AccountsSection businessUnits={businessUnits} divisions={divisions} banks={banks} currencies={currencies} />
      <UsersSection />
    </div>
  );
}
