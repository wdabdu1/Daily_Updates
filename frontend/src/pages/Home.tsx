import { useEffect, useState } from "react";
import { api } from "../api/client";
import { formatPlain, formatSDG, formatUSD } from "../format";

interface FxSnapshotRate {
  rate_type: string;
  usd_rate: string | null;
  usd_rate_date: string | null;
  aed_rate: string | null;
  aed_rate_date: string | null;
}

interface HomeSummary {
  as_of: string | null;
  total_receivables_sdg: string;
  total_dues_sdg: string;
  gap_sdg: string;
  gap_pct: string | null;
  usd_sdg_rate: string | null;
  usd_sdg_rate_date: string | null;
  gap_usd_equivalent: string | null;
  total_receivables_usd: string | null;
  total_dues_usd: string | null;
  status: "covered" | "shortfall" | "no_data";
  unconverted_account_count: number;
  notes: string | null;
  fx_snapshot: FxSnapshotRate[];
}

interface CoverBreakdownRow {
  group_label: string;
  total_receivables_sdg: string | null;
  total_dues_sdg: string;
  gap_sdg: string | null;
  status: "covered" | "shortfall" | null;
  pct_of_total_receivables: string | null;
}
interface CoverBreakdownResponse {
  rows: CoverBreakdownRow[];
  total: CoverBreakdownRow;
  receivables_applicable: boolean;
}

interface ReceivablesContributionRow {
  business_unit_name: string;
  division_name: string | null;
  total_receivables_sdg: string;
  pct_of_total_receivables: string | null;
  total_dues_sdg: string;
}
interface ReceivablesContributionResponse {
  rows: ReceivablesContributionRow[];
  total: ReceivablesContributionRow;
}

type CoverGroupBy = "bank" | "division" | "business_unit";

const FX_RATE_TYPES = ["Market", "CBOS", "Pricing"];

const COVER_GROUP_LABELS: Record<CoverGroupBy, string> = {
  bank: "Bank",
  division: "Division",
  business_unit: "Business Unit",
};

// Plain proportion (no +/- sign, unlike formatPct which is used for gap_pct
// where the sign is meaningful).
function formatShare(value: string | null): string {
  if (value === null) return "—";
  const n = parseFloat(value);
  if (Number.isNaN(n)) return "—";
  return `${n.toFixed(2)}%`;
}

function dash(value: string | null, fmt: (v: string) => string): string {
  return value === null ? "—" : fmt(value);
}

export function Home() {
  const [summary, setSummary] = useState<HomeSummary | null>(null);
  const [coverGroupBy, setCoverGroupBy] = useState<CoverGroupBy>("business_unit");
  const [coverBreakdown, setCoverBreakdown] = useState<CoverBreakdownResponse | null>(null);
  const [contribution, setContribution] = useState<ReceivablesContributionResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api
      .get<HomeSummary>("/api/home/summary")
      .then((res) => setSummary(res.data))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    api
      .get<CoverBreakdownResponse>(`/api/home/breakdown?group_by=${coverGroupBy}`)
      .then((res) => setCoverBreakdown(res.data));
  }, [coverGroupBy]);

  useEffect(() => {
    api
      .get<ReceivablesContributionResponse>("/api/home/receivables-contribution")
      .then((res) => setContribution(res.data));
  }, []);

  if (loading && !summary) {
    return (
      <div className="page">
        <p className="muted">Loading...</p>
      </div>
    );
  }

  if (!summary) return null;

  const gap = parseFloat(summary.gap_sdg);
  const isCovered = gap >= 0;
  const fxByType = new Map(summary.fx_snapshot.map((f) => [f.rate_type, f]));

  return (
    <div className="page">
      <div className="page__header">
        <h1 className="page__title">Treasury Coverage &amp; Liquidity</h1>
        <p className="page__subtitle">
          {summary.as_of
            ? `Receivables as of ${summary.as_of}`
            : "No receivables have been recorded yet"}
        </p>
      </div>

      <div className="stat-grid" style={{ marginBottom: "1.25rem" }}>
        {FX_RATE_TYPES.map((rt) => {
          const f = fxByType.get(rt);
          return (
            <div className="stat-card" key={rt}>
              <p className="stat-card__label">{rt} Rate — USD/SDG</p>
              <p className="stat-card__value">{f?.usd_rate ? formatPlain(f.usd_rate, 0) : "—"}</p>
              <p className="stat-card__meta" style={{ fontSize: "0.78rem" }}>
                AED/SDG: {f?.aed_rate ? formatPlain(f.aed_rate, 0) : "—"}
              </p>
            </div>
          );
        })}
      </div>

      {summary.status === "shortfall" && (
        <div className="alert alert--negative">
          Exposure alert: today's receivables exceed active bank dues (coverage) by{" "}
          {formatSDG(summary.gap_sdg.replace(/^-/, ""))}.
        </div>
      )}
      {summary.status === "covered" && (
        <div className="alert alert--positive">
          Active bank dues cover today's receivables.
        </div>
      )}
      {summary.status === "no_data" && (
        <div className="alert alert--neutral">{summary.notes}</div>
      )}
      {summary.status !== "no_data" && summary.notes && (
        <div className="alert alert--neutral">{summary.notes}</div>
      )}

      <div className="stat-grid">
        <div className="stat-card">
          <p className="stat-card__label">Total Receivables</p>
          <p className="stat-card__value">{formatSDG(summary.total_receivables_sdg, 0)}</p>
          <p className="stat-card__meta">{formatUSD(summary.total_receivables_usd, 0)}</p>
        </div>
        <div className="stat-card">
          <p className="stat-card__label">Active Bank Dues</p>
          <p className="stat-card__value">{formatSDG(summary.total_dues_sdg, 0)}</p>
          <p className="stat-card__meta">{formatUSD(summary.total_dues_usd, 0)}</p>
        </div>
        <div className="stat-card">
          <p className="stat-card__label">Available Cover</p>
          <p
            className="stat-card__value"
            style={{ color: isCovered ? "var(--color-positive)" : "var(--color-negative)" }}
          >
            {formatSDG(summary.gap_sdg, 0)}
          </p>
          <p className="stat-card__meta">{formatUSD(summary.gap_usd_equivalent, 0)}</p>
        </div>
      </div>

      <div className="card">
        <div className="toolbar">
          <h2 className="section-title" style={{ marginBottom: 0 }}>
            Cover by {COVER_GROUP_LABELS[coverGroupBy]}
          </h2>
          <div className="filters">
            <select value={coverGroupBy} onChange={(e) => setCoverGroupBy(e.target.value as CoverGroupBy)}>
              <option value="bank">Bank</option>
              <option value="division">Division</option>
              <option value="business_unit">Business Unit</option>
            </select>
          </div>
        </div>
        <p className="muted" style={{ marginTop: 0 }}>
          {coverGroupBy === "bank"
            ? "Active Dues distribution by Bank. Receivables have no bank concept (they're recorded per Division), so Receivables/Gap aren't shown here — switch to Division or Business Unit for the full comparison."
            : "A unit in shortfall while the company total is covered means another unit is effectively subsidizing it."}
        </p>
        {!coverBreakdown || coverBreakdown.rows.length === 0 ? (
          <div className="empty-state">No accounts registered yet.</div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>{COVER_GROUP_LABELS[coverGroupBy]}</th>
                <th className="numeric">Active Dues</th>
                <th className="numeric">Receivables</th>
                <th className="numeric">Gap</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {coverBreakdown.rows.map((row) => (
                <tr key={row.group_label}>
                  <td>{row.group_label}</td>
                  <td className="numeric">{formatSDG(row.total_dues_sdg)}</td>
                  <td className="numeric">{dash(row.total_receivables_sdg, formatSDG)}</td>
                  <td className="numeric">{dash(row.gap_sdg, formatSDG)}</td>
                  <td>
                    {row.status ? (
                      <span className={"badge " + (row.status === "covered" ? "badge--positive" : "badge--negative")}>
                        {row.status === "covered" ? "Covered" : "Shortfall"}
                      </span>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                </tr>
              ))}
              <tr style={{ fontWeight: 700 }}>
                <td>{coverBreakdown.total.group_label}</td>
                <td className="numeric">{formatSDG(coverBreakdown.total.total_dues_sdg)}</td>
                <td className="numeric">{dash(coverBreakdown.total.total_receivables_sdg, formatSDG)}</td>
                <td className="numeric">{dash(coverBreakdown.total.gap_sdg, formatSDG)}</td>
                <td>
                  {coverBreakdown.total.status ? (
                    <span className={"badge " + (coverBreakdown.total.status === "covered" ? "badge--positive" : "badge--negative")}>
                      {coverBreakdown.total.status === "covered" ? "Covered" : "Shortfall"}
                    </span>
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
              </tr>
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <div className="toolbar">
          <h2 className="section-title" style={{ marginBottom: 0 }}>
            Receivables Contribution
          </h2>
        </div>
        <p className="muted" style={{ marginTop: 0 }}>
          How much each division (and its Business Unit) contributes to total receivables. Dues on
          an account with no division link land in a trailing "Unassigned" row rather than being
          dropped.
        </p>
        {!contribution || contribution.rows.length === 0 ? (
          <div className="empty-state">No divisions registered yet.</div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Business Unit</th>
                <th>Division</th>
                <th className="numeric">Receivables</th>
                <th className="numeric">% of Total Receivables</th>
                <th className="numeric">Active Dues</th>
              </tr>
            </thead>
            <tbody>
              {contribution.rows.map((row, i) => (
                <tr key={`${row.business_unit_name}-${row.division_name ?? i}`}>
                  <td>{row.business_unit_name}</td>
                  <td>{row.division_name ?? "—"}</td>
                  <td className="numeric">{formatSDG(row.total_receivables_sdg)}</td>
                  <td className="numeric">{formatShare(row.pct_of_total_receivables)}</td>
                  <td className="numeric">{formatSDG(row.total_dues_sdg)}</td>
                </tr>
              ))}
              <tr style={{ fontWeight: 700 }}>
                <td colSpan={2}>{contribution.total.business_unit_name}</td>
                <td className="numeric">{formatSDG(contribution.total.total_receivables_sdg)}</td>
                <td className="numeric">{formatShare(contribution.total.pct_of_total_receivables)}</td>
                <td className="numeric">{formatSDG(contribution.total.total_dues_sdg)}</td>
              </tr>
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
