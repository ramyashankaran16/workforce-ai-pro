import { analyticsApi } from "../api/endpoints";
import { useApi } from "../hooks/useApi";
import { Card, StatTile } from "../components/ui/Card";
import { AsyncBoundary, EmptyState } from "../components/ui/States";
import { CHART_COLOURS, percent } from "../utils/format";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Line,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

const axis = { fontSize: 12, fill: "#64748b" };

export default function Attrition() {
  const overview = useApi(() => analyticsApi.overview(12), []);
  const byDepartment = useApi(analyticsApi.byDepartment, []);
  const byTenure = useApi(analyticsApi.byTenure, []);
  const reasons = useApi(analyticsApi.exitReasons, []);
  const drivers = useApi(analyticsApi.drivers, []);

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-xl font-semibold text-ink-900">Attrition analytics</h1>
        <p className="mt-0.5 text-sm text-ink-500">
          Rolling twelve months. Voluntary and involuntary exits are counted
          separately — only one of them is something the business can influence.
        </p>
      </header>

      <AsyncBoundary
        loading={overview.loading}
        error={overview.error}
        onRetry={overview.refetch}
      >
        {overview.data && (
          <>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <StatTile
                label="Attrition rate"
                value={percent(overview.data.attrition_rate_percent)}
                hint={`${overview.data.exits_in_window} exits in 12 months`}
              />
              <StatTile
                label="Voluntary"
                value={percent(overview.data.voluntary_rate_percent)}
                hint={`${overview.data.voluntary_exits} resignations`}
              />
              <StatTile
                label="Active headcount"
                value={overview.data.active_headcount}
              />
              <StatTile
                label="At high risk"
                value={overview.data.employees_at_high_risk}
                accent={
                  overview.data.employees_at_high_risk > 0
                    ? "text-orange-600"
                    : "text-ink-900"
                }
              />
            </div>

            <Card
              title="Headcount and exits over time"
              subtitle="Joiners against leavers, month by month"
            >
              <ResponsiveContainer width="100%" height={280}>
                <AreaChart data={overview.data.trend}>
                  <defs>
                    <linearGradient id="headcount" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#6366f1" stopOpacity={0.25} />
                      <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                  <XAxis dataKey="period" tick={axis} />
                  <YAxis yAxisId="left" tick={axis} />
                  <YAxis yAxisId="right" orientation="right" tick={axis} />
                  <Tooltip />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Area
                    yAxisId="left"
                    type="monotone"
                    dataKey="headcount"
                    name="Headcount"
                    stroke="#6366f1"
                    fill="url(#headcount)"
                  />
                  <Line
                    yAxisId="right"
                    type="monotone"
                    dataKey="exits"
                    name="Exits"
                    stroke="#ef4444"
                    strokeWidth={2}
                    dot={false}
                  />
                  <Line
                    yAxisId="right"
                    type="monotone"
                    dataKey="joiners"
                    name="Joiners"
                    stroke="#10b981"
                    strokeWidth={2}
                    dot={false}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </Card>
          </>
        )}
      </AsyncBoundary>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card
          title="Attrition by tenure"
          subtitle="The first year usually dominates — which makes it an onboarding question, not a hiring one"
        >
          <AsyncBoundary
            loading={byTenure.loading}
            error={byTenure.error}
            isEmpty={byTenure.data?.length === 0}
          >
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={byTenure.data ?? []}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                <XAxis dataKey="tenure_band" tick={axis} />
                <YAxis tick={axis} unit="%" />
                <Tooltip formatter={(value) => `${value}%`} />
                <Bar
                  dataKey="attrition_rate_percent"
                  name="Attrition rate"
                  radius={[6, 6, 0, 0]}
                >
                  {(byTenure.data ?? []).map((entry, index) => (
                    <Cell
                      key={entry.tenure_band}
                      fill={index === 0 ? "#ef4444" : "#6366f1"}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </AsyncBoundary>
        </Card>

        <Card title="Attrition by department" subtitle="Ranked by rate">
          <AsyncBoundary
            loading={byDepartment.loading}
            error={byDepartment.error}
            isEmpty={byDepartment.data?.length === 0}
          >
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={byDepartment.data ?? []} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" horizontal={false} />
                <XAxis type="number" tick={axis} unit="%" />
                <YAxis
                  type="category"
                  dataKey="department_name"
                  tick={axis}
                  width={110}
                />
                <Tooltip formatter={(value) => `${value}%`} />
                <Bar
                  dataKey="attrition_rate_percent"
                  name="Attrition rate"
                  fill="#f59e0b"
                  radius={[0, 6, 6, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </AsyncBoundary>
        </Card>

        <Card title="Stated exit reasons" subtitle="From recorded exits">
          <AsyncBoundary
            loading={reasons.loading}
            error={reasons.error}
            isEmpty={reasons.data?.length === 0}
            empty={<EmptyState title="No exits recorded yet" />}
          >
            <ul className="space-y-3">
              {(reasons.data ?? []).map((reason, index) => (
                <li key={reason.reason}>
                  <div className="flex justify-between text-sm">
                    <span className="truncate pr-3 text-ink-700">{reason.reason}</span>
                    <span className="shrink-0 tabular-nums text-ink-500">
                      {reason.count} · {reason.percent}%
                    </span>
                  </div>
                  <div className="mt-1 h-2 overflow-hidden rounded-full bg-ink-100">
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${reason.percent}%`,
                        background: CHART_COLOURS[index % CHART_COLOURS.length],
                      }}
                    />
                  </div>
                </li>
              ))}
            </ul>
          </AsyncBoundary>
        </Card>

        <Card
          title="Model drivers"
          subtitle="Global feature importance — describes the model, not any one person"
        >
          <AsyncBoundary loading={drivers.loading} error={drivers.error}>
            {!drivers.data?.model ? (
              <EmptyState
                title="No model deployed"
                hint="Train and deploy a model to see which features carry weight."
              />
            ) : (
              <>
                <p className="mb-3 text-xs text-ink-500">
                  {drivers.data.model.name} v{drivers.data.model.version} ·{" "}
                  {drivers.data.model.algorithm.replace(/_/g, " ")}
                </p>
                <ResponsiveContainer width="100%" height={230}>
                  <BarChart data={drivers.data.drivers.slice(0, 8)} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" horizontal={false} />
                    <XAxis type="number" tick={axis} />
                    <YAxis
                      type="category"
                      dataKey="feature"
                      tick={{ fontSize: 10, fill: "#64748b" }}
                      width={140}
                    />
                    <Tooltip />
                    <Bar dataKey="importance" fill="#8b5cf6" radius={[0, 6, 6, 0]} />
                  </BarChart>
                </ResponsiveContainer>
                <p className="mt-2 text-xs text-ink-400">{drivers.data.note}</p>
              </>
            )}
          </AsyncBoundary>
        </Card>
      </div>
    </div>
  );
}
