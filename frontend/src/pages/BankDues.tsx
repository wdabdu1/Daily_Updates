import { useEffect, useMemo, useState } from "react";
import { NumericFormat } from "react-number-format";
import { api, downloadXlsx, errMsg } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { formatSDG, formatWhole } from "../format";

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

interface AccountOption {
  id: number;
  account_name: string;
  account_number: string;
  bank_short_name: string | null;
  business_unit_name: string | null;
}

interface DivisionOption {
  id: number;
  name: string;
  business_unit_id: number;
  business_unit_name: string;
}

interface DivisionReceivableFormRow {
  division_id: number;
  division_name: string;
  business_unit_name: string;
  default_amount: string;
  default_amount_date: string | null;
  is_recorded_for_date: boolean;
}

interface DivisionReceivableTableRow {
  position_date: string;
  amounts: Record<string, string>;
  total: string;
}

function todayStr() {
  return new Date().toISOString().slice(0, 10);
}

function accountLabel(a: AccountOption) {
  const bu = a.business_unit_name ? ` -- ${a.business_unit_name}` : "";
  return `${a.bank_short_name || "?"} / ${a.account_name} (${a.account_number})${bu}`;
}

// A due is "overdue" once its date has passed and it's still Active (i.e.
// nobody marked it settled/paid in time) -- purely a visual flag here,
// Settled dues already drop out of every total server-side (see home.py /
// analysis.py's `status == "Active"` filters) once "Mark Settled" is used.
function isOverdue(d: BankDue): boolean {
  return d.status === "Active" && !!d.due_date && d.due_date < todayStr();
}

type SortKey =
  | "business_unit_name"
  | "division_name"
  | "bank_short_name"
  | "account_number"
  | "due_date"
  | "facility_type"
  | "amount"
  | "status";

const SORT_COLUMNS: { key: SortKey; label: string; numeric?: boolean }[] = [
  { key: "business_unit_name", label: "Business Unit" },
  { key: "division_name", label: "Division" },
  { key: "bank_short_name", label: "Bank" },
  { key: "account_number", label: "Account" },
  { key: "due_date", label: "Due Date" },
  { key: "facility_type", label: "Facility" },
  { key: "amount", label: "Amount", numeric: true },
  { key: "status", label: "Status" },
];

type DueFilters = Record<Exclude<SortKey, "amount">, string>;
const EMPTY_FILTERS: DueFilters = {
  business_unit_name: "",
  division_name: "",
  bank_short_name: "",
  account_number: "",
  due_date: "",
  facility_type: "",
  status: "",
};

function dueSortValue(d: BankDue, key: SortKey): string | number {
  switch (key) {
    case "amount":
      return parseFloat(d.amount);
    case "business_unit_name":
      return (d.business_unit_name || "Unassigned").toLowerCase();
    case "division_name":
      return (d.division_name || "").toLowerCase();
    case "bank_short_name":
      return (d.bank_short_name || "").toLowerCase();
    case "account_number":
      return (d.account_number || "").toLowerCase();
    case "due_date":
      return d.due_date || "";
    case "facility_type":
      return (d.facility_type || "").toLowerCase();
    case "status":
      return d.status;
  }
}

function DuesSection() {
  const { canWrite } = useAuth();
  const [dues, setDues] = useState<BankDue[]>([]);
  const [accounts, setAccounts] = useState<AccountOption[]>([]);
  const [loading, setLoading] = useState(true);

  const [sortKey, setSortKey] = useState<SortKey>("due_date");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [filters, setFilters] = useState<DueFilters>(EMPTY_FILTERS);

  const emptyDraft = { account_id: "", due_date: todayStr(), facility_type: "", amount: "" };
  const [draft, setDraft] = useState(emptyDraft);
  const [addBusy, setAddBusy] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  const [editingId, setEditingId] = useState<number | null>(null);
  const [editDraft, setEditDraft] = useState({
    account_id: "",
    due_date: "",
    facility_type: "",
    amount: "",
    status: "Active",
  });
  const [editBusy, setEditBusy] = useState(false);
  const [rowError, setRowError] = useState<string | null>(null);

  function refresh() {
    setLoading(true);
    api
      .get<BankDue[]>("/api/dues")
      .then((res) => setDues(res.data))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);
  useEffect(() => {
    if (canWrite) {
      api.get<AccountOption[]>("/api/accounts").then((res) => {
        setAccounts(res.data);
        setDraft((d) => (d.account_id ? d : { ...d, account_id: res.data[0] ? String(res.data[0].id) : "" }));
      });
    }
  }, [canWrite]);

  const filteredDues = useMemo(() => {
    return dues.filter((d) => {
      if (
        !(d.business_unit_name || "Unassigned").toLowerCase().includes(filters.business_unit_name.toLowerCase())
      )
        return false;
      if (!(d.division_name || "").toLowerCase().includes(filters.division_name.toLowerCase())) return false;
      if (!(d.bank_short_name || "").toLowerCase().includes(filters.bank_short_name.toLowerCase())) return false;
      if (!(d.account_number || "").toLowerCase().includes(filters.account_number.toLowerCase())) return false;
      if (!(d.due_date || "").includes(filters.due_date)) return false;
      if (!(d.facility_type || "").toLowerCase().includes(filters.facility_type.toLowerCase())) return false;
      if (filters.status === "Overdue" && !isOverdue(d)) return false;
      if (filters.status && filters.status !== "Overdue" && d.status !== filters.status) return false;
      return true;
    });
  }, [dues, filters]);

  const sortedDues = useMemo(() => {
    const copy = [...filteredDues];
    copy.sort((a, b) => {
      const av = dueSortValue(a, sortKey);
      const bv = dueSortValue(b, sortKey);
      if (av < bv) return sortDir === "asc" ? -1 : 1;
      if (av > bv) return sortDir === "asc" ? 1 : -1;
      return 0;
    });
    return copy;
  }, [filteredDues, sortKey, sortDir]);

  const filteredTotal = useMemo(
    () => filteredDues.reduce((sum, d) => sum + (parseFloat(d.amount) || 0), 0),
    [filteredDues]
  );

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  function setFilter(key: keyof DueFilters, value: string) {
    setFilters((prev) => ({ ...prev, [key]: value }));
  }

  const hasActiveFilters = Object.values(filters).some((v) => v);

  async function settle(id: number) {
    await api.post(`/api/dues/${id}/settle`);
    refresh();
  }

  async function addDue() {
    if (!draft.account_id || !draft.due_date || !draft.facility_type.trim() || !draft.amount) return;
    setAddBusy(true);
    setAddError(null);
    try {
      await api.post("/api/dues", {
        account_id: Number(draft.account_id),
        due_date: draft.due_date,
        facility_type: draft.facility_type.trim(),
        amount: draft.amount,
      });
      setDraft({ ...emptyDraft, account_id: draft.account_id });
      refresh();
    } catch (e: any) {
      setAddError(errMsg(e, "Couldn't add this due."));
    } finally {
      setAddBusy(false);
    }
  }

  function startEdit(d: BankDue) {
    setEditingId(d.id);
    setEditDraft({
      account_id: String(d.account_id),
      due_date: d.due_date || "",
      facility_type: d.facility_type || "",
      amount: d.amount,
      status: d.status,
    });
    setRowError(null);
  }

  async function saveEdit(id: number) {
    setEditBusy(true);
    setRowError(null);
    try {
      await api.put(`/api/dues/${id}`, {
        account_id: Number(editDraft.account_id),
        due_date: editDraft.due_date,
        facility_type: editDraft.facility_type.trim(),
        amount: editDraft.amount,
        status: editDraft.status,
      });
      setEditingId(null);
      refresh();
    } catch (e: any) {
      setRowError(errMsg(e, "Couldn't update this due."));
    } finally {
      setEditBusy(false);
    }
  }

  async function removeDue(d: BankDue) {
    if (!window.confirm(`Delete this due (${d.account_number}, ${d.due_date}, ${d.facility_type})?`)) return;
    setRowError(null);
    try {
      await api.delete(`/api/dues/${d.id}`);
      refresh();
    } catch (e: any) {
      setRowError(errMsg(e, "Couldn't delete this due."));
    }
  }

  return (
    <div className="card">
      <h2 className="section-title">Bank Dues</h2>

      {canWrite && (
        <>
          <p className="muted" style={{ marginTop: 0 }}>
            Add a due below, or use the filters and column headers in the table to check totals
            for a subset of dues.
          </p>
          <div className="toolbar">
            <div className="filters">
              <button
                className="btn btn--ghost"
                onClick={() => downloadXlsx("/api/dues/export", "bank_dues.xlsx")}
              >
                Download as Excel
              </button>
              {hasActiveFilters && (
                <button className="btn btn--ghost" onClick={() => setFilters(EMPTY_FILTERS)}>
                  Clear Filters
                </button>
              )}
            </div>
          </div>
        </>
      )}

      {rowError && <p className="error-text">{rowError}</p>}

      {loading ? (
        <p className="muted">Loading...</p>
      ) : dues.length === 0 ? (
        <div className="empty-state">No bank dues recorded yet.</div>
      ) : (
        <div style={{ overflowX: "auto" }}>
        <table className="data-table">
          <thead>
            <tr>
              {SORT_COLUMNS.map((col) => (
                <th
                  key={col.key}
                  className={col.numeric ? "numeric" : undefined}
                  style={{ cursor: "pointer", userSelect: "none", whiteSpace: "nowrap" }}
                  onClick={() => toggleSort(col.key)}
                  title="Click to sort"
                >
                  {col.label}
                  {sortKey === col.key ? (sortDir === "asc" ? " ▲" : " ▼") : ""}
                </th>
              ))}
              {canWrite && <th></th>}
            </tr>
            <tr>
              <th>
                <input
                  className="filter-input"
                  value={filters.business_unit_name}
                  onChange={(e) => setFilter("business_unit_name", e.target.value)}
                  placeholder="Filter..."
                />
              </th>
              <th>
                <input
                  className="filter-input"
                  value={filters.division_name}
                  onChange={(e) => setFilter("division_name", e.target.value)}
                  placeholder="Filter..."
                />
              </th>
              <th>
                <input
                  className="filter-input"
                  value={filters.bank_short_name}
                  onChange={(e) => setFilter("bank_short_name", e.target.value)}
                  placeholder="Filter..."
                />
              </th>
              <th>
                <input
                  className="filter-input"
                  value={filters.account_number}
                  onChange={(e) => setFilter("account_number", e.target.value)}
                  placeholder="Filter..."
                />
              </th>
              <th>
                <input
                  className="filter-input"
                  value={filters.due_date}
                  onChange={(e) => setFilter("due_date", e.target.value)}
                  placeholder="YYYY-MM-DD"
                />
              </th>
              <th>
                <input
                  className="filter-input"
                  value={filters.facility_type}
                  onChange={(e) => setFilter("facility_type", e.target.value)}
                  placeholder="Filter..."
                />
              </th>
              <th className="numeric"></th>
              <th>
                <select value={filters.status} onChange={(e) => setFilter("status", e.target.value)}>
                  <option value="">All</option>
                  <option value="Active">Active</option>
                  <option value="Settled">Settled</option>
                  <option value="Overdue">Overdue</option>
                </select>
              </th>
              {canWrite && <th></th>}
            </tr>
          </thead>
          <tbody>
            {sortedDues.map((d) =>
              editingId === d.id ? (
                <tr key={d.id}>
                  <td colSpan={4}>
                    <select value={editDraft.account_id} onChange={(e) => setEditDraft({ ...editDraft, account_id: e.target.value })}>
                      {accounts.map((a) => (
                        <option key={a.id} value={a.id}>
                          {accountLabel(a)}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <input
                      type="date"
                      value={editDraft.due_date}
                      onChange={(e) => setEditDraft({ ...editDraft, due_date: e.target.value })}
                    />
                  </td>
                  <td>
                    <input
                      value={editDraft.facility_type}
                      onChange={(e) => setEditDraft({ ...editDraft, facility_type: e.target.value })}
                    />
                  </td>
                  <td className="numeric">
                    <NumericFormat
                      style={{ textAlign: "right" }}
                      thousandSeparator=","
                      decimalScale={2}
                      allowNegative={false}
                      value={editDraft.amount}
                      onValueChange={(v) => setEditDraft({ ...editDraft, amount: v.value })}
                    />
                  </td>
                  <td>
                    <select value={editDraft.status} onChange={(e) => setEditDraft({ ...editDraft, status: e.target.value })}>
                      <option value="Active">Active</option>
                      <option value="Settled">Settled</option>
                    </select>
                  </td>
                  <td>
                    <div className="row-actions">
                      <button className="btn btn--small" onClick={() => saveEdit(d.id)} disabled={editBusy}>
                        Save
                      </button>
                      <button className="btn btn--small" onClick={() => setEditingId(null)} disabled={editBusy}>
                        Cancel
                      </button>
                    </div>
                  </td>
                </tr>
              ) : (
                <tr key={d.id} style={isOverdue(d) ? { background: "var(--color-negative-bg)" } : undefined}>
                  <td>{d.business_unit_name || "Unassigned"}</td>
                  <td>{d.division_name || "—"}</td>
                  <td>{d.bank_short_name}</td>
                  <td>{d.account_number}</td>
                  <td>{d.due_date}</td>
                  <td>{d.facility_type}</td>
                  <td className="numeric">{formatSDG(d.amount)}</td>
                  <td>
                    <span
                      className={"badge " + (d.status === "Active" ? "badge--negative" : "badge--neutral")}
                      title={isOverdue(d) ? "Past its due date and still Active" : undefined}
                    >
                      {isOverdue(d) ? "Overdue" : d.status}
                    </span>
                  </td>
                  {canWrite && (
                    <td>
                      <div className="row-actions">
                        {d.status === "Active" && (
                          <button className="btn btn--ghost btn--small" onClick={() => settle(d.id)}>
                            Mark Settled
                          </button>
                        )}
                        <button className="btn btn--ghost btn--small" onClick={() => startEdit(d)}>
                          Edit
                        </button>
                        <button className="btn btn--danger btn--small" onClick={() => removeDue(d)}>
                          Delete
                        </button>
                      </div>
                    </td>
                  )}
                </tr>
              )
            )}
            <tr style={{ fontWeight: 700 }}>
              <td colSpan={6}>
                Total ({filteredDues.length} of {dues.length} row{dues.length === 1 ? "" : "s"})
              </td>
              <td className="numeric">{formatSDG(filteredTotal)}</td>
              <td></td>
              {canWrite && <td></td>}
            </tr>
          </tbody>
        </table>
        </div>
      )}

      {canWrite && (
        <div style={{ marginTop: "1.25rem", paddingTop: "1.25rem", borderTop: "1px solid var(--color-border)" }}>
          <p className="field-label" style={{ marginBottom: "0.75rem" }}>
            Add a due manually
          </p>
          <div className="form-grid">
            <div>
              <label className="field-label">Account</label>
              <select value={draft.account_id} onChange={(e) => setDraft({ ...draft, account_id: e.target.value })}>
                {accounts.length === 0 && <option value="">No accounts yet</option>}
                {accounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {accountLabel(a)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="field-label">Due Date</label>
              <input type="date" value={draft.due_date} onChange={(e) => setDraft({ ...draft, due_date: e.target.value })} />
            </div>
            <div>
              <label className="field-label">Facility Type</label>
              <input
                value={draft.facility_type}
                onChange={(e) => setDraft({ ...draft, facility_type: e.target.value })}
                placeholder="e.g. Overdraft"
              />
            </div>
            <div>
              <label className="field-label">Amount</label>
              <NumericFormat
                thousandSeparator=","
                decimalScale={2}
                allowNegative={false}
                value={draft.amount}
                onValueChange={(v) => setDraft({ ...draft, amount: v.value })}
              />
            </div>
          </div>
          <button
            className="btn btn--primary"
            style={{ marginTop: "0.75rem" }}
            disabled={!draft.account_id || !draft.due_date || !draft.facility_type.trim() || !draft.amount || addBusy}
            onClick={addDue}
          >
            {addBusy ? "Adding..." : "Add Due"}
          </button>
          {accounts.length === 0 && (
            <p className="muted" style={{ marginTop: "0.5rem" }}>
              No accounts registered yet -- add one under Settings, or it'll be created automatically the first time you import a due for it.
            </p>
          )}
          {addError && <p className="error-text">{addError}</p>}
        </div>
      )}
    </div>
  );
}

function DivisionReceivablesSection() {
  const { canWrite } = useAuth();
  const [divisions, setDivisions] = useState<DivisionOption[]>([]);
  const [tableRows, setTableRows] = useState<DivisionReceivableTableRow[]>([]);
  const [loadingTable, setLoadingTable] = useState(true);

  const [editing, setEditing] = useState(false);
  const [positionDate, setPositionDate] = useState(todayStr());
  const [formRows, setFormRows] = useState<DivisionReceivableFormRow[]>([]);
  const [amounts, setAmounts] = useState<Record<number, string>>({});
  const [loadingForm, setLoadingForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);

  function refreshTable() {
    setLoadingTable(true);
    return api
      .get<DivisionReceivableTableRow[]>("/api/receivables/divisions/table")
      .then((res) => setTableRows(res.data))
      .finally(() => setLoadingTable(false));
  }

  useEffect(() => {
    api.get<DivisionOption[]>("/api/receivables/divisions/list").then((res) => setDivisions(res.data));
    refreshTable();
  }, []);

  async function startUpdate() {
    setLoadingForm(true);
    setSaved(null);
    try {
      const res = await api.get<DivisionReceivableFormRow[]>("/api/receivables/divisions/form", {
        params: { position_date: positionDate },
      });
      setFormRows(res.data);
      const initial: Record<number, string> = {};
      res.data.forEach((r) => (initial[r.division_id] = r.default_amount));
      setAmounts(initial);
      setEditing(true);
    } finally {
      setLoadingForm(false);
    }
  }

  async function save() {
    setSaving(true);
    try {
      await api.post("/api/receivables/divisions/save", {
        position_date: positionDate,
        rows: formRows.map((r) => ({ division_id: r.division_id, amount: amounts[r.division_id] || "0" })),
      });
      setSaved(`Saved as the ${positionDate} division position.`);
      setEditing(false);
      refreshTable();
    } finally {
      setSaving(false);
    }
  }

  const isToday = positionDate === todayStr();

  return (
    <div className="card">
      <h2 className="section-title">Division Receivables</h2>
      <p className="muted" style={{ marginTop: 0 }}>
        Each division's total accumulated cash position -- across whichever banks it holds it in,
        or cash in hand -- recorded as a single SDG figure rather than tied to one bank/account.
        This feeds the Home page's coverage comparison. Pick a date (defaults to today), use
        Today's Update to prefill every division with its most recently recorded amount, adjust
        what's changed, and save -- the record is added to the history table below.
      </p>
      {saved && <div className="alert alert--positive">{saved}</div>}
      {!editing && canWrite && (
        <div style={{ display: "flex", gap: "0.75rem", alignItems: "flex-end", marginBottom: "1.5rem" }}>
          <div>
            <label className="field-label">Date</label>
            <input
              type="date"
              value={positionDate}
              max={todayStr()}
              onChange={(e) => setPositionDate(e.target.value)}
            />
          </div>
          <button className="btn btn--primary" onClick={startUpdate} disabled={loadingForm || divisions.length === 0}>
            {loadingForm ? "Loading..." : isToday ? "Today's Update" : "Edit This Day"}
          </button>
          {divisions.length === 0 && (
            <p className="muted" style={{ margin: 0 }}>
              No divisions registered yet -- add one under Settings.
            </p>
          )}
        </div>
      )}
      {editing && (
        <>
          <p className="muted" style={{ marginTop: 0 }}>
            Editing the position for <strong>{positionDate}</strong>
            {isToday ? "" : " (a past day)"}.
          </p>
          {formRows.length === 0 ? (
            <div className="empty-state">No divisions registered yet.</div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Business Unit</th>
                  <th>Division</th>
                  <th className="numeric">Last Recorded</th>
                  <th className="numeric">{isToday ? "Today's Position" : "Position for This Day"}</th>
                </tr>
              </thead>
              <tbody>
                {formRows.map((r) => (
                  <tr key={r.division_id}>
                    <td>{r.business_unit_name}</td>
                    <td>{r.division_name}</td>
                    <td className="numeric">
                      {r.is_recorded_for_date
                        ? "(already recorded for this day)"
                        : `${formatSDG(r.default_amount)}${r.default_amount_date ? ` (${r.default_amount_date})` : ""}`}
                    </td>
                    <td className="numeric">
                      <NumericFormat
                        style={{ textAlign: "right" }}
                        thousandSeparator=","
                        decimalScale={2}
                        allowNegative={false}
                        inputMode="decimal"
                        value={amounts[r.division_id] ?? ""}
                        onValueChange={(v) =>
                          setAmounts((prev) => ({ ...prev, [r.division_id]: v.value }))
                        }
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <div style={{ marginTop: "1rem", display: "flex", gap: "0.75rem" }}>
            <button className="btn btn--primary" onClick={save} disabled={saving || formRows.length === 0}>
              {saving ? "Saving..." : "Save"}
            </button>
            <button className="btn btn--ghost" onClick={() => setEditing(false)} disabled={saving}>
              Cancel
            </button>
          </div>
        </>
      )}

      <div style={{ marginTop: "1.5rem", paddingTop: "1.5rem", borderTop: "1px solid var(--color-border)" }}>
        <p className="field-label" style={{ marginBottom: "0.75rem" }}>
          History
        </p>
        {loadingTable ? (
          <p className="muted">Loading...</p>
        ) : tableRows.length === 0 ? (
          <div className="empty-state">No division positions recorded yet.</div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="data-table" style={{ fontSize: "0.8rem" }}>
              <thead>
                <tr>
                  <th>Date</th>
                  {divisions.map((d) => (
                    <th className="numeric" key={d.id} style={{ whiteSpace: "nowrap" }}>
                      {d.business_unit_name} - {d.name} (SDG)
                    </th>
                  ))}
                  <th className="numeric">Total (SDG)</th>
                </tr>
              </thead>
              <tbody>
                {tableRows.map((row) => (
                  <tr key={row.position_date}>
                    <td>{row.position_date}</td>
                    {divisions.map((d) => (
                      <td className="numeric" key={d.id}>
                        {row.amounts[String(d.id)] !== undefined ? (
                          formatWhole(row.amounts[String(d.id)])
                        ) : (
                          <span className="muted">—</span>
                        )}
                      </td>
                    ))}
                    <td className="numeric" style={{ fontWeight: 700 }}>
                      {formatWhole(row.total)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

export function BankDues() {
  return (
    <div className="page">
      <div className="page__header">
        <h1 className="page__title">Bank Dues &amp; Receivables</h1>
        <p className="page__subtitle">
          Register what's owed to banks and keep each division's receivables position current.
        </p>
      </div>
      <DuesSection />
      <DivisionReceivablesSection />
    </div>
  );
}
