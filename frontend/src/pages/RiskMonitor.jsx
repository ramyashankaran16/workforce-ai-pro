import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { RefreshCw } from "lucide-react";
import { riskApi } from "../api/endpoints";
import { useApi } from "../hooks/useApi";
import { Card } from "../components/ui/Card";
import Badge from "../components/ui/Badge";
import { Pagination, Table } from "../components/ui/Table";
import { AsyncBoundary, EmptyState } from "../components/ui/States";
import { useAuth } from "../context/AuthContext";
import { percent } from "../utils/format";

export default function RiskMonitor() {
  const navigate = useNavigate();
  const { can } = useAuth();
  const [page, setPage] = useState(1);
  const [level, setLevel] = useState("");
  const [evaluating, setEvaluating] = useState(false);
  const [message, setMessage] = useState(null);

  const scores = useApi(
    () => riskApi.scores({ page, size: 15, ...(level ? { risk_level: level } : {}) }),
    [page, level]
  );
  const heatmap = useApi(riskApi.heatmap, [], { immediate: can("risk:read_all") });
  const alerts = useApi(() => riskApi.alerts({ size: 5, status: "new" }), []);

  const evaluate = async () => {
    setEvaluating(true);
    setMessage(null);
    try {
      const result = await riskApi.evaluate();
      setMessage(
        `Scored ${result.evaluated} employees — ${result.critical} critical, ` +
          `${result.high} high, ${result.medium} medium, ${result.low} low.`
      );
      scores.refetch().catch(() => {});
      heatmap.refetch().catch(() => {});
    } catch (error) {
      setMessage(error.message);
    } finally {
      setEvaluating(false);
    }
  };

  const columns = [
    {
      key: "employee_id",
      header: "Employee",
      render: (row) => (
        <button
          className="font-medium text-brand-700 hover:underline"
          onClick={() => navigate(`/employees/${row.employee_id}`)}
        >
          #{row.employee_id}
        </button>
      ),
    },
    {
      key: "overall_score",
      header: "Score",
      render: (row) => (
        <div className="flex items-center gap-2">
          <span className="w-9 tabular-nums text-sm font-medium">
            {row.overall_score.toFixed(0)}
          </span>
          <div className="h-1.5 w-24 overflow-hidden rounded-full bg-ink-100">
            <div
              className="h-full rounded-full bg-brand-500"
              style={{ width: `${row.overall_score}%` }}
            />
          </div>
        </div>
      ),
    },
    {
      key: "risk_level",
      header: "Band",
      render: (row) => <Badge risk={row.risk_level}>{row.risk_level}</Badge>,
    },
    {
      key: "trend",
      header: "Trend",
      render: (row) => (
        <span
          className={
            row.trend === "worsening"
              ? "text-red-600"
              : row.trend === "improving"
              ? "text-emerald-600"
              : "text-ink-500"
          }
        >
          {row.trend}
          {row.score_change ? ` (${row.score_change > 0 ? "+" : ""}${row.score_change})` : ""}
        </span>
      ),
    },
    {
      key: "summary",
      header: "Why",
      className: "max-w-md",
      render: (row) => (
        <span className="line-clamp-2 text-xs text-ink-600">{row.summary || "—"}</span>
      ),
    },
  ];

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-ink-900">Risk monitor</h1>
          <p className="mt-0.5 text-sm text-ink-500">
            Model probability blended with compensation, engagement, workload,
            attendance, performance and tenure.
          </p>
        </div>
        {can("risk:manage") && (
          <button className="btn-primary" onClick={evaluate} disabled={evaluating}>
            <RefreshCw className={`h-4 w-4 ${evaluating ? "animate-spin" : ""}`} />
            {evaluating ? "Scoring" : "Re-evaluate all"}
          </button>
        )}
      </header>

      {message && (
        <div className="rounded-lg bg-brand-50 px-4 py-3 text-sm text-brand-700">
          {message}
        </div>
      )}

      {can("risk:read_all") && (
        <Card title="Risk by department" subtitle="Ranked by average score">
          <AsyncBoundary
            loading={heatmap.loading}
            error={heatmap.error}
            isEmpty={heatmap.data?.length === 0}
            empty={<EmptyState title="Nothing scored yet" hint="Run an evaluation first." />}
          >
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {(heatmap.data ?? []).map((dept) => (
                <div key={dept.department_id} className="rounded-lg border border-ink-200 p-4">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-sm font-medium text-ink-800">
                      {dept.department_name}
                    </p>
                    <span className="tabular-nums text-sm font-semibold text-ink-900">
                      {dept.average_risk_score.toFixed(0)}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-ink-500">
                    {dept.headcount} people · {dept.high_risk_count} at risk (
                    {percent(dept.high_risk_percent)})
                  </p>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-ink-100">
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${dept.average_risk_score}%`,
                        background:
                          dept.average_risk_score >= 55 ? "#f97316" : "#6366f1",
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </AsyncBoundary>
        </Card>
      )}

      {alerts.data?.items?.length > 0 && (
        <Card title="Open alerts" subtitle="Newest first">
          <ul className="space-y-2.5">
            {alerts.data.items.map((alert) => (
              <li
                key={alert.id}
                className="flex items-start justify-between gap-3 rounded-lg border border-ink-200 px-4 py-3"
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium text-ink-800">{alert.title}</p>
                  <p className="mt-0.5 text-xs text-ink-500">{alert.message}</p>
                </div>
                <Badge risk={alert.risk_level}>{alert.risk_level}</Badge>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <div className="card overflow-hidden">
        <div className="flex flex-wrap items-center gap-3 border-b border-ink-100 px-5 py-4">
          <h2 className="text-sm font-semibold text-ink-800">Scored employees</h2>
          <select
            className="field ml-auto w-auto"
            value={level}
            onChange={(event) => {
              setPage(1);
              setLevel(event.target.value);
            }}
          >
            <option value="">All bands</option>
            {["critical", "high", "medium", "low"].map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </div>

        <AsyncBoundary
          loading={scores.loading}
          error={scores.error}
          onRetry={scores.refetch}
          isEmpty={scores.data?.items?.length === 0}
          empty={
            <EmptyState
              title="No risk scores yet"
              hint="Select Re-evaluate all to score the workforce."
            />
          }
        >
          <Table columns={columns} rows={scores.data?.items ?? []} />
          <Pagination meta={scores.data?.meta} onChange={setPage} />
        </AsyncBoundary>
      </div>
    </div>
  );
}
