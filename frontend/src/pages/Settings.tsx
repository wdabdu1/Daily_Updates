import { useEffect, useState } from "react";
import { api } from "../api/client";

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
}

function errMsg(e: any, fallback: string) {
  const detail = e?.response?.data?.detail;
  return typeof detail === "string" && detail ? detail : fallback;
}

// ---------------------------------------------------------------- Business Units
function BusinessUnitsSection({ onChange }: { onChange: () => void }) {
  const [items, setItems] = useState<BusinessUnit[]>([]);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  return (
    <div className="card">
      <h2 className="section-title">Business Units</h2>
      <table className="data-table">
        <thead>
          <tr>
            <th>Name</th>
          </tr>
        </thead>
        <tbody>
          {items.map((b) => (
            <tr key={b.id}>
              <td>{b.name}</td>
            </tr>
          ))}
          {items.length === 0 && (
            <tr>
              <td className="muted">No business units yet.</td>
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

  const buName = (id: number) => businessUnits.find((b) => b.id === id)?.name || `#${id}`;

  return (
    <div className="card">
      <h2 className="section-title">Divisions</h2>
      <table className="data-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Business Unit</th>
          </tr>
        </thead>
        <tbody>
          {items.map((d) => (
            <tr key={d.id}>
              <td>{d.name}</td>
              <td>{buName(d.business_unit_id)}</td>
            </tr>
          ))}
          {items.length === 0 && (
            <tr>
              <td className="muted" colSpan={2}>
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

  return (
    <div className="card">
      <h2 className="section-title">Banks</h2>
      <table className="data-table">
        <thead>
          <tr>
            <th>Short Name</th>
            <th>Full Name</th>
          </tr>
        </thead>
        <tbody>
          {items.map((b) => (
            <tr key={b.id}>
              <td>{b.short_name}</td>
              <td>{b.full_name}</td>
            </tr>
          ))}
          {items.length === 0 && (
            <tr>
              <td className="muted" colSpan={2}>
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

  return (
    <div className="card">
      <h2 className="section-title">Currencies</h2>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginBottom: "1rem" }}>
        {items.map((c) => (
          <span key={c.code} className="badge">
            {c.code}
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
function CurrencyPairsSection({ currencies }: { currencies: Currency[] }) {
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
    } catch (e: any) {
      setError(errMsg(e, "Couldn't add this currency pair."));
    } finally {
      setBusy(false);
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
            </tr>
          ))}
          {items.length === 0 && (
            <tr>
              <td className="muted" colSpan={2}>
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

// ----------------------------------------------------------------------- Users
function UsersSection() {
  const [items, setItems] = useState<AppUser[]>([]);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("ReadWrite");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resetting, setResetting] = useState<number | null>(null);
  const [resetPw, setResetPw] = useState("");
  const [resetMsg, setResetMsg] = useState<string | null>(null);

  function refresh() {
    api.get<AppUser[]>("/api/settings/users").then((res) => setItems(res.data));
  }
  useEffect(refresh, []);

  async function add() {
    if (!username.trim() || !password) return;
    setBusy(true);
    setError(null);
    try {
      await api.post("/api/settings/users", { username: username.trim(), password, role });
      setUsername("");
      setPassword("");
      setRole("ReadWrite");
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
            <th>Role</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {items.map((u) => (
            <tr key={u.id}>
              <td>{u.username}</td>
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
                    <button className="btn" onClick={() => doReset(u.id)} disabled={!resetPw}>
                      Save
                    </button>
                    <button
                      className="btn"
                      onClick={() => {
                        setResetting(null);
                        setResetPw("");
                      }}
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <button
                    className="btn"
                    onClick={() => {
                      setResetting(u.id);
                      setResetPw("");
                      setResetMsg(null);
                    }}
                  >
                    Reset password
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {resetMsg && <p className="muted">{resetMsg}</p>}
      <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem", alignItems: "flex-end" }}>
        <div>
          <label className="field-label">Username</label>
          <input value={username} onChange={(e) => setUsername(e.target.value)} />
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

// ------------------------------------------------------------------ Danger Zone
function DangerZone() {
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
      setError(errMsg(e, "Reset failed."));
    } finally {
      setBusy(false);
    }
  }

  const canConfirm = confirmText.trim().toUpperCase() === "WIPE";

  return (
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
            <option value="transactions">Transactions only (Bank Dues, Receivables, FX Rates)</option>
            <option value="everything">Everything (also Business Units, Divisions, Banks, Master Accounts)</option>
          </select>
        </div>
        <div>
          <label className="field-label">Type WIPE to confirm</label>
          <input value={confirmText} onChange={(e) => setConfirmText(e.target.value)} />
        </div>
      </div>
      {error && <p className="error-text">{error}</p>}
      {result && (
        <div className="alert alert--positive" style={{ marginTop: "1rem" }}>
          {result}
        </div>
      )}
      <button
        className="btn btn--primary"
        style={{ marginTop: "1rem", background: "var(--color-negative)" }}
        disabled={!canConfirm || busy}
        onClick={runReset}
      >
        {busy ? "Clearing..." : "Clear Data"}
      </button>
    </div>
  );
}

export function Settings() {
  const [businessUnits, setBusinessUnits] = useState<BusinessUnit[]>([]);
  const [currencies, setCurrencies] = useState<Currency[]>([]);
  const [refreshKey, setRefreshKey] = useState(0);

  function refreshShared() {
    api.get<BusinessUnit[]>("/api/settings/business-units").then((res) => setBusinessUnits(res.data));
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
          out, but predefining them here avoids surprises and typos.
        </p>
      </div>

      <BusinessUnitsSection onChange={bump} />
      <DivisionsSection businessUnits={businessUnits} onChange={bump} />
      <BanksSection onChange={bump} />
      <CurrenciesSection onChange={bump} />
      <CurrencyPairsSection currencies={currencies} />
      <UsersSection />
      <DangerZone />
    </div>
  );
}
