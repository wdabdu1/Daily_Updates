import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { LineChart } from "../components/LineChart";
import { formatSDG } from "../format";

interface CurrencyPair {
  id: number;
  base_currency: string;
  quote_currency: string;
  supports_extended_rates: boolean;
  is_default: boolean;
}
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
interface FxRateRow {
  rate_date: string;
  rate_type: string;
  rate: string;
  is_carried_forward: boolean;
}
interface CoverTrendPoint {
  position_date: string;
  total_receivables_sdg: number;
  total_dues_sdg: number;
  gap_sdg: number;
}

const RATE_COLORS: Record<string, string> = {
  Market: "#0f6fb0",
  CBOS: "#7a4fc9",
  Pricing: "#d97a1f",
};

const PERIOD_PRESETS = [
  { label: "Last month", months: 1 },
  { label: "Last 3 months", months: 3 },
  { label: "Last 6 months", months: 6 },
  { label: "Last 12 months", months: 12 },
];

function periodRange(months: number) {
  const end = new Date();
  const start = new Date();
  start.setMonth(start.getMonth() - months);
  const fmt = (d: Date) => d.toISOString().slice(0, 10);
  return { start: fmt(start), end: fmt(end) };
}

function FxAnalysis() {
  const [pairs, setPairs] = useState<CurrencyPair[]>([]);
  const [pairId, setPairId] = useState<number | null>(null);
  const [months, setMonths] = useState(3);
  const [series, setSeries] = useState<{ label: string; color: string; points: { x: string; y: number }[] }[]>([]);
  const [loading, setLoading] = useState(false);

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
    if (!pair) return;
    const types = pair.supports_extended_rates ? ["Market", "CBOS", "Pricing"] : ["Market"];
    const { start, end } = periodRange(months);
    setLoading(true);
    Promise.all(
      types.map((t) =>
        api
          .get<FxRateRow[]>("/api/fx/rates/table", {
            params: { currency_pair_id: pairId, rate_type: t, start, end },
          })
          .then((res) => ({
            label: t,
            color: RATE_COLORS[t] || "#888",
            points: res.data.map((r) => ({ x: r.rate_date, y: parseFloat(r.rate) })),
          }))
      )
    )
      .then(setSeries)
      .finally(() => setLoading(false));
  }, [pairId, months, pairs]);

  const selectedPair = pairs.find((p) => p.id === pairId);

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
          <select value={months} onChange={(e) => setMonths(Number(e.target.value))}>
            {PERIOD_PRESETS.map((p) => (
              <option key={p.months} value={p.months}>
                {p.label}
              </option>
            ))}
          </select>
        </div>
      </div>
      <p className="muted" style={{ marginTop: 0 }}>
        {selectedPair?.supports_extended_rates
          ? "Comparing Market, CBOS and Pricing rates over the selected period."
          : "This pair only carries a Market Rate (CBOS/Pricing only apply to SDG pairs)."}
      </p>
      {loading ? <p className="muted">Loading...</p> : <LineChart series={series} />}
    </div>
  );
}

function CoverAnalysis() {
  const [businessUnits, setBusinessUnits] = useState<BusinessUnit[]>([]);
  const [divisions, setDivisions] = useState<Division[]>([]);
  const [banks, setBanks] = useState<Bank[]>([]);
  const [buId, setBuId] = useState<string>("");
  const [divId, setDivId] = useState<string>("");
  const [bankId, setBankId] = useState<string>("");
  const [months, setMonths] = useState(3);
  const [points, setPoints] = useState<CoverTrendPoint[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.get<BusinessUnit[]>("/api/settings/business-units").then((res) => setBusinessUnits(res.data));
    api.get<Division[]>("/api/settings/divisions").then((res) => setDivisions(res.data));
    api.get<Bank[]>("/api/settings/banks").then((res) => setBanks(res.data));
  }, []);

  useEffect(() => {
    const { start, end } = periodRange(months);
    setLoading(true);
    api
      .get<CoverTrendPoint[]>("/api/analysis/cover-trend", {
        params: {
          start,
          end,
          business_unit_id: buId || undefined,
          division_id: divId || undefined,
          bank_id: bankId || undefined,
        },
      })
      .then((res) => setPoints(res.data))
      .finally(() => setLoading(false));
  }, [buId, divId, bankId, months]);

  const filteredDivisions = useMemo(
    () => (buId ? divisions.filter((d) => d.business_unit_id === Number(buId)) : divisions),
    [divisions, buId]
  );

  const series = [
    {
      label: "Active Dues",
      color: "#1a7f4c",
      points: points.map((p) => ({ x: p.position_date, y: p.total_dues_sdg })),
    },
    {
      label: "Receivables",
      color: "#c0392b",
      points: points.map((p) => ({ x: p.position_date, y: p.total_receivables_sdg })),
    },
  ];

  return (
    <div className="card">
      <div className="toolbar">
        <h2 className="section-title" style={{ marginBottom: 0 }}>
          Cover Analysis
        </h2>
        <div className="filters">
          <select value={buId} onChange={(e) => { setBuId(e.target.value); setDivId(""); }}>
            <option value="">All Business Units</option>
            {businessUnits.map((b) => (
              <option key={b.id} value={b.id}>{b.name}</option>
            ))}
          </select>
          <select value={divId} onChange={(e) => setDivId(e.target.value)}>
            <option value="">All Divisions</option>
            {filteredDivisions.map((d) => (
              <option key={d.id} value={d.id}>{d.name}</option>
            ))}
          </select>
          <select value={bankId} onChange={(e) => setBankId(e.target.value)}>
            <option value="">All Banks</option>
            {banks.map((b) => (
              <option key={b.id} value={b.id}>{b.short_name}</option>
            ))}
          </select>
          <select value={months} onChange={(e) => setMonths(Number(e.target.value))}>
            {PERIOD_PRESETS.map((p) => (
              <option key={p.months} value={p.months}>{p.label}</option>
            ))}
          </select>
        </div>
      </div>
      <p className="muted" style={{ marginTop: 0 }}>
        Active Dues reflects the current total (dues aren't logged historically day-by-day);
        Receivables is the real daily trend from your saved snapshots.
      </p>
      {loading ? (
        <p className="muted">Loading...</p>
      ) : points.length === 0 ? (
        <div className="empty-state">No receivables recorded yet for this filter/period.</div>
      ) : (
        <>
          <LineChart series={series} />
          <table className="data-table" style={{ marginTop: "1.25rem" }}>
            <thead>
              <tr>
                <th>Date</th>
                <th className="numeric">Receivables</th>
                <th className="numeric">Active Dues</th>
                <th className="numeric">Gap</th>
              </tr>
            </thead>
            <tbody>
              {points
                .slice()
                .reverse()
                .map((p) => (
                  <tr key={p.position_date}>
                    <td>{p.position_date}</td>
                    <td className="numeric">{formatSDG(p.total_receivables_sdg)}</td>
                    <td className="numeric">{formatSDG(p.total_dues_sdg)}</td>
                    <td className="numeric">{formatSDG(p.gap_sdg)}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </>
      )}
    </div>
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
