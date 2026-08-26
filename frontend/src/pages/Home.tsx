import { useEffect, useState } from "react";
import { api } from "../api/client";
import { formatPct, formatSDG, formatUSD } from "../format";

interface HomeSummary {
  as_of: string | null;
  total_receivables_sdg: string;
  total_dues_sdg: string;
  gap_sdg: string;
  gap_pct: string | null;
  usd_sdg_rate: string | null;
  usd_sdg_rate_date: string | null;
  gap_usd_equivalent: string | null;
  status: "covered" | "shortfall" | "no_data";
  unconverted_account_count: number;
  notes: string | null;
}

interface BreakdownRow {
  group_label: string;
  total_receivables_sdg: string;
  total_dues_sdg: string;
  gap_sdg: string;
  status: "covered" | "shortfall";
  pct_of_total_receivables: string | null;
}

type GroupBy = "business_unit" | "division" | "bank";

// Plain proportion (no +/- sign, unlike formatPct which is used for gap_pct
// where the sign is meaningful).
function formatShare(value: string | null): string {
  if (value === null) return "—";
  const n = parseFloat(value);
  if (Number.isNaN(n)) return "—";
  return `${n.toFixed(2)}%`;
}

export function Home() {
  const [summary, setSummary] = useState<HomeSummary | null>(null);
  const [breakdown, setBreakdown] = useState<BreakdownRow[]>([]);
  const [groupBy, setGroupBy] = useState<GroupBy>("business_unit");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api.get<HomeSummary>("/api/home/summary"),
      api.get<BreakdownRow[]>(`/api/home/breakdown?group_by=${groupBy}`),
    ])
      .then(([s, b]) => {
        setSummary(s.data);
        setBreakdown(b.data);
      })
      .finally(() => setLoading(false));
  }, [groupBy]);

  if (loading && !summary) {
    return (
      <div className="page">
        <p className="muted">Loading...</p>
      </div>
    );
  }

  if (!summary) return null;

  const maxAbsGap = Math.max(
    1,
    ...breakdown.map((r) => Math.abs(parseFloat(r.gap_sdg)))
  );

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
          <p className="stat-card__value">{formatSDG(summary.total_receivables_sdg)}</p>
        </div>
        <div className="stat-card">
          <p className="stat-card__label">Active Bank Dues</p>
          <p className="stat-card__value">{formatSDG(summary.total_dues_sdg)}</p>
        </div>
        <div className="stat-card">
          <p className="stat-card__label">Cover (Dues − Receivables)</p>
          <p className="stat-card__value">{formatSDG(summary.gap_sdg)}</p>
          <p className="stat-card__meta">
            <span
              className={
                "badge " +
                (parseFloat(summary.gap_sdg) >= 0 ? "badge--positive" : "badge--negative")
              }
            >
              {formatPct(summary.gap_pct)}
            </span>
          </p>
        </div>
        <div className="stat-card">
          <p className="stat-card__label">Gap, USD Equivalent</p>
          <p className="stat-card__value">{formatUSD(summary.gap_usd_equivalent)}</p>
          <p className="stat-card__meta">
            {summary.usd_sdg_rate
              ? `USD/SDG ${summary.usd_sdg_rate} as of ${summary.usd_sdg_rate_date}`
              : "No USD/SDG rate recorded yet"}
          </p>
        </div>
      </div>

      <div className="card">
        <div className="toolbar">
          <h2 className="section-title" style={{ marginBottom: 0 }}>
            Cover by {groupBy === "business_unit" ? "Business Unit" : groupBy === "division" ? "Division" : "Bank"}
          </h2>
          <div className="filters">
            <select value={groupBy} onChange={(e) => setGroupBy(e.target.value as GroupBy)}>
              <option value="business_unit">Business Unit</option>
              <option value="division">Division</option>
              <option value="bank">Bank</option>
            </select>
          </div>
        </div>

        {breakdown.length === 0 ? (
          <div className="empty-state">No accounts registered yet.</div>
        ) : (
          <div>
            {breakdown.map((row) => {
              const gap = parseFloat(row.gap_sdg);
              const widthPct = Math.min(100, (Math.abs(gap) / maxAbsGap) * 100);
              return (
                <div className="bar-row" key={row.group_label}>
                  <div className="bar-row__label" title={row.group_label}>
                    {row.group_label}
                  </div>
                  <div className="bar-track">
                    <div
                      className={"bar-fill " + (gap >= 0 ? "bar-fill--positive" : "bar-fill--negative")}
                      style={{ width: `${widthPct}%` }}
                    />
                  </div>
                  <div className="bar-row__value">{formatSDG(row.gap_sdg)}</div>
                </div>
              );
            })}
          </div>
        )}
        <p className="muted" style={{ fontSize: "0.82rem", marginTop: "0.75rem" }}>
          A unit in shortfall while the company total is covered means another unit is
          effectively subsidizing it — see Analysis for the full drill-down.
        </p>
      </div>

      {breakdown.length > 0 && (
        <div className="card">
          <h2 className="section-title">Receivables Contribution</h2>
          <p className="muted" style={{ marginTop: 0 }}>
            How much each {groupBy === "business_unit" ? "business unit" : groupBy === "division" ? "division" : "bank"}{" "}
            contributes to total receivables — useful when Dues can't yet be attributed the same
            way (an "Unassigned" row means those dues are only linked to a Bank/Account so far, not
            a Business Unit or Division).
          </p>
          <table className="data-table">
            <thead>
              <tr>
                <th>{groupBy === "business_unit" ? "Business Unit" : groupBy === "division" ? "Division" : "Bank"}</th>
                <th className="numeric">Receivables</th>
                <th className="numeric">% of Total Receivables</th>
                <th className="numeric">Active Dues</th>
              </tr>
            </thead>
            <tbody>
              {breakdown.map((row) => (
                <tr key={row.group_label}>
                  <td>{row.group_label}</td>
                  <td className="numeric">{formatSDG(row.total_receivables_sdg)}</td>
                  <td className="numeric">{formatShare(row.pct_of_total_receivables)}</td>
                  <td className="numeric">{formatSDG(row.total_dues_sdg)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
