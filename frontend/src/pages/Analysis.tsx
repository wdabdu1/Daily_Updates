import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { LineChart } from "../components/LineChart";
import { StackedBarChart, type StackedBarSpec } from "../components/StackedBarChart";
import { formatSDG } from "../format";

interface CurrencyPair {
  id: number;
  base_currency: string;
  quote_currency: string;
  supports_extended_rates: boolean;
  is_default: boolean;
}
interface FxRateRow {
  rate_date: string;
  rate_type: string;
  rate: string;
  is_carried_forward: boolean;
}
interface CoverSnapshotSlice {
  label: string;
  amount: string;
  color: string;
}
interface CoverSnapshot {
  position_date: string | null;
  // "Overall" = Credit Sales (PDC) + Cash Balances combined, by division.
  receivables_by_division: CoverSnapshotSlice[];
  dues_by_bank: CoverSnapshotSlice[];
  total_receivables_sdg: string;
  total_dues_sdg: string;
  gap_sdg: string;
  cover_pct: string | null;
  pdc_by_division: CoverSnapshotSlice[];
  total_pdc_sdg: string;
  total_cash_sdg: string;
  gap_pdc_sdg: string;
  cover_pct_pdc: string | null;
}
interface DivisionReceivableTableRow {
  position_date: string;
  amounts: Record<string, string>;
  total: string;
}

const RATE_COLORS: Record<string, string> = {
  Market: "#0f6fb0",
  CBOS: "#7a4fc9",
  Pricing: "#d97a1f",
};

function todayStr() {
  return new Date().toISOString().slice(0, 10);
}
// Last-resort fallback fetch-window start, mirroring NO_DATA_FALLBACK_START
// in FxRates.tsx -- only used if a pair genuinely has no rates on file yet
// (before /api/fx/rates/earliest resolves, or if it returns null).
const NO_DATA_FALLBACK_START = todayStr();

// Round 19: these mirror the identically-named helpers in FxRates.tsx
// (kept as separate copies since the two pages don't currently share a
// date-utils module) -- used to power the same Year/Quarter/Month period
// filter here that the Rate History table already has.
function yearKey(dateStr: string) {
  return dateStr.slice(0, 4);
}
function monthKey(dateStr: string) {
  return dateStr.slice(0, 7);
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

function FxAnalysis() {
  const [pairs, setPairs] = useState<CurrencyPair[]>([]);
  const [pairId, setPairId] = useState<number | null>(null);
  // Round 19: fetch window start, resolved per-pair via /rates/earliest
  // (same pattern as FxRates.tsx) instead of a fixed lookback window --
  // this used to be capped at "Last 12 months" max, so a specific older
  // year (or the full history) was never reachable at all.
  const [historyStart, setHistoryStart] = useState<string | null>(null);
  const [rawSeries, setRawSeries] = useState<{ label: string; color: string; points: { x: string; y: number }[] }[]>([]);
  const [loading, setLoading] = useState(false);

  // Defaults to the current year -- same reasoning as FxRates.tsx defaulting
  // its Rate History table to the current month: a fresh page load should
  // show something immediately relevant, not the oldest data on file. The
  // user can still switch to All/Quarter/Month manually.
  const [periodType, setPeriodType] = useState<"All" | "Year" | "Quarter" | "Month">("Year");
  const [periodValue, setPeriodValue] = useState<string>("");

  useEffect(() => {
    api.get<CurrencyPair[]>("/api/settings/currency-pairs").then((res) => {
      setPairs(res.data);
      const def = res.data.find((p) => p.is_default) || res.data[0];
      if (def) setPairId(def.id);
    });
  }, []);

  useEffect(() => {
    if (pairId == null) return;
    setHistoryStart(null);
    api
      .get<{ earliest: string | null }>("/api/fx/rates/earliest", { params: { currency_pair_id: pairId } })
      .then((res) => setHistoryStart(res.data.earliest ?? NO_DATA_FALLBACK_START));
  }, [pairId]);

  // Fetches each rate type's FULL history once per pair (from its earliest
  // entry to today), same as the Rate History table does -- the Year/
  // Quarter/Month filter below then narrows it client-side with no extra
  // round-trips, so switching periods is instant.
  useEffect(() => {
    if (pairId == null || !historyStart) return;
    const pair = pairs.find((p) => p.id === pairId);
    if (!pair) return;
    const types = pair.supports_extended_rates ? ["Market", "CBOS", "Pricing"] : ["Market"];
    setLoading(true);
    Promise.all(
      types.map((t) =>
        api
          .get<FxRateRow[]>("/api/fx/rates/table", {
            params: { currency_pair_id: pairId, rate_type: t, start: historyStart, end: todayStr() },
          })
          .then((res) => ({
            label: t,
            color: RATE_COLORS[t] || "#888",
            points: res.data.map((r) => ({ x: r.rate_date, y: parseFloat(r.rate) })),
          }))
      )
    )
      .then(setRawSeries)
      .finally(() => setLoading(false));
  }, [pairId, historyStart, pairs]);

  const selectedPair = pairs.find((p) => p.id === pairId);

  const allDates = useMemo(
    () => Array.from(new Set(rawSeries.flatMap((s) => s.points.map((p) => p.x)))).sort(),
    [rawSeries]
  );
  const years = useMemo(() => Array.from(new Set(allDates.map(yearKey))).sort().reverse(), [allDates]);
  const quarters = useMemo(() => Array.from(new Set(allDates.map(quarterKey))).sort().reverse(), [allDates]);
  const monthsAvailable = useMemo(() => Array.from(new Set(allDates.map(monthKey))).sort().reverse(), [allDates]);

  useEffect(() => {
    if (periodType === "Year" && !years.includes(periodValue)) setPeriodValue(years[0] ?? "");
    if (periodType === "Quarter" && !quarters.includes(periodValue)) setPeriodValue(quarters[0] ?? "");
    if (periodType === "Month" && !monthsAvailable.includes(periodValue)) setPeriodValue(monthsAvailable[0] ?? "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [periodType, years, quarters, monthsAvailable]);

  const series = useMemo(() => {
    if (periodType === "All") return rawSeries;
    const inPeriod = (x: string) => {
      if (periodType === "Year") return yearKey(x) === periodValue;
      if (periodType === "Quarter") return quarterKey(x) === periodValue;
      return monthKey(x) === periodValue;
    };
    return rawSeries.map((s) => ({ ...s, points: s.points.filter((p) => inPeriod(p.x)) }));
  }, [rawSeries, periodType, periodValue]);

  return (
    <div className="card">
      <div className="toolbar">
        <h2 className="section-title" style={{ marginBottom: 0 }}>
          FX Analysis
        </h2>
        <div className="filters">
          <select value={pairId ?? ""} onChange={(e) => setPairId(Number(e.target.value))}>
            {pairs.map((p) => (
              <option key={p.id} value={p.id}>
                {p.base_currency}/{p.quote_currency}
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
        </div>
      </div>
      <p className="muted" style={{ marginTop: 0 }}>
        {selectedPair?.supports_extended_rates
          ? "Comparing Market, CBOS and Pricing rates over the selected period."
          : "This pair only carries a Market Rate (CBOS/Pricing only apply to SDG pairs)."}
      </p>
      {loading || !historyStart ? <p className="muted">Loading...</p> : <LineChart series={series} />}
    </div>
  );
}

// Plain proportion, no +/- sign -- unlike the Gap, "cover %" (Active Dues /
// Receivables, per the user's own definition) has no natural sign, just a
// number that's higher or lower than 100%.
function formatCoverPct(value: string | null): string {
  if (value === null) return "—";
  const n = parseFloat(value);
  if (Number.isNaN(n)) return "—";
  return `${n.toFixed(2)}%`;
}

function coverGapBar(gapStr: string): StackedBarSpec {
  const gap = parseFloat(gapStr);
  const isCovered = gap >= 0;
  return {
    key: "gap",
    label: "Gap (Dues − Receivables)",
    total: Math.abs(gap),
    slices: [],
    soloColor: isCovered ? "var(--color-positive)" : "var(--color-negative)",
    totalLabel: `${isCovered ? "+" : "-"}${formatSDG(Math.abs(gap))}\n(${isCovered ? "Covered" : "Shortfall"})`,
  };
}

function SliceLegend({ title, slices, emptyText }: { title: string; slices: CoverSnapshotSlice[]; emptyText: string }) {
  return (
    <div>
      <p className="field-label" style={{ marginBottom: "0.5rem" }}>{title}</p>
      {slices.length === 0 ? (
        <p className="muted" style={{ fontSize: "0.85rem" }}>{emptyText}</p>
      ) : (
        slices.map((s) => (
          <div key={s.label} style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.85rem", padding: "0.2rem 0" }}>
            <span style={{ width: 12, height: 12, borderRadius: 2, background: s.color, display: "inline-block", flexShrink: 0 }} />
            <span style={{ flex: 1 }}>{s.label}</span>
            <span className="numeric" style={{ fontVariantNumeric: "tabular-nums" }}>{formatSDG(s.amount)}</span>
          </div>
        ))
      )}
    </div>
  );
}

function CoverAnalysis() {
  const [availableDates, setAvailableDates] = useState<string[]>([]);
  const [positionDate, setPositionDate] = useState<string>("");
  const [snapshot, setSnapshot] = useState<CoverSnapshot | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    Promise.all([
      api.get<DivisionReceivableTableRow[]>("/api/receivables/divisions/table"),
      api.get<DivisionReceivableTableRow[]>("/api/cash/divisions/table"),
    ]).then(([pdcRes, cashRes]) => {
      const dates = Array.from(
        new Set([...pdcRes.data.map((r) => r.position_date), ...cashRes.data.map((r) => r.position_date)])
      )
        .sort()
        .reverse();
      setAvailableDates(dates);
      if (dates.length) setPositionDate(dates[0]);
    });
  }, []);

  useEffect(() => {
    setLoading(true);
    api
      .get<CoverSnapshot>("/api/analysis/cover-snapshot", {
        params: positionDate ? { position_date: positionDate } : {},
      })
      .then((res) => setSnapshot(res.data))
      .finally(() => setLoading(false));
  }, [positionDate]);

  const overallBars: StackedBarSpec[] = useMemo(() => {
    if (!snapshot) return [];
    return [
      {
        key: "receivables",
        label: "Receivables (PDC + Cash, by Division)",
        total: parseFloat(snapshot.total_receivables_sdg),
        slices: snapshot.receivables_by_division.map((s) => ({ label: s.label, amount: parseFloat(s.amount), color: s.color })),
      },
      {
        key: "dues",
        label: "Active Dues (by Bank)",
        total: parseFloat(snapshot.total_dues_sdg),
        slices: snapshot.dues_by_bank.map((s) => ({ label: s.label, amount: parseFloat(s.amount), color: s.color })),
      },
      coverGapBar(snapshot.gap_sdg),
    ];
  }, [snapshot]);

  const pdcBars: StackedBarSpec[] = useMemo(() => {
    if (!snapshot) return [];
    return [
      {
        key: "pdc",
        label: "Credit Sales / PDC (by Division)",
        total: parseFloat(snapshot.total_pdc_sdg),
        slices: snapshot.pdc_by_division.map((s) => ({ label: s.label, amount: parseFloat(s.amount), color: s.color })),
      },
      {
        key: "dues",
        label: "Active Dues (by Bank)",
        total: parseFloat(snapshot.total_dues_sdg),
        slices: snapshot.dues_by_bank.map((s) => ({ label: s.label, amount: parseFloat(s.amount), color: s.color })),
      },
      coverGapBar(snapshot.gap_pdc_sdg),
    ];
  }, [snapshot]);

  const dateSelector = (
    <select value={positionDate} onChange={(e) => setPositionDate(e.target.value)} disabled={availableDates.length === 0}>
      {availableDates.length === 0 && <option value="">No positions recorded yet</option>}
      {availableDates.map((d) => (
        <option key={d} value={d}>{d}</option>
      ))}
    </select>
  );

  if (!loading && (!snapshot || availableDates.length === 0)) {
    return (
      <div className="card">
        <h2 className="section-title">Overall Cover Analysis</h2>
        <div className="empty-state">
          No receivables or cash positions recorded yet -- use Bank Dues &amp; Receivables to record today's position.
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="card">
        <div className="toolbar">
          <h2 className="section-title" style={{ marginBottom: 0 }}>
            Overall Cover Analysis
          </h2>
          <div className="filters">{dateSelector}</div>
        </div>
        <p className="muted" style={{ marginTop: 0 }}>
          A single day's snapshot: Credit Sales (PDC) and Cash Balances combined, stacked by
          Division, against Active Dues stacked by Bank, and the Gap between them. Cover % is
          Active Dues ÷ Receivables.
        </p>
        {loading || !snapshot ? (
          <p className="muted">Loading...</p>
        ) : (
          <>
            <div className="stat-card" style={{ maxWidth: 220, marginBottom: "1rem" }}>
              <p className="stat-card__label">Cover %</p>
              <p className="stat-card__value">{formatCoverPct(snapshot.cover_pct)}</p>
            </div>
            <StackedBarChart bars={overallBars} />
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem", marginTop: "1rem" }}>
              <SliceLegend
                title="Receivables (PDC + Cash) by Division"
                slices={snapshot.receivables_by_division}
                emptyText="No divisions recorded for this date."
              />
              <SliceLegend title="Active Dues by Bank" slices={snapshot.dues_by_bank} emptyText="No active dues recorded." />
            </div>
          </>
        )}
      </div>

      <div className="card">
        <div className="toolbar">
          <h2 className="section-title" style={{ marginBottom: 0 }}>
            Cover Analysis
          </h2>
          <div className="filters">{dateSelector}</div>
        </div>
        <p className="muted" style={{ marginTop: 0 }}>
          The same comparison with Cash Balances removed -- Credit Sales (PDC) only, stacked by
          Division, against Active Dues.
        </p>
        {loading || !snapshot ? (
          <p className="muted">Loading...</p>
        ) : (
          <>
            <div className="stat-card" style={{ maxWidth: 220, marginBottom: "1rem" }}>
              <p className="stat-card__label">Cover % (PDC only)</p>
              <p className="stat-card__value">{formatCoverPct(snapshot.cover_pct_pdc)}</p>
            </div>
            <StackedBarChart bars={pdcBars} />
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem", marginTop: "1rem" }}>
              <SliceLegend
                title="Credit Sales (PDC) by Division"
                slices={snapshot.pdc_by_division}
                emptyText="No divisions recorded for this date."
              />
              <SliceLegend title="Active Dues by Bank" slices={snapshot.dues_by_bank} emptyText="No active dues recorded." />
            </div>
          </>
        )}
      </div>
    </>
  );
}

export function Analysis() {
  return (
    <div className="page">
      <div className="page__header">
        <h1 className="page__title">Analysis</h1>
        <p className="page__subtitle">FX rate trends and the cover position drill-down.</p>
      </div>
      <CoverAnalysis />
      <FxAnalysis />
    </div>
  );
}
