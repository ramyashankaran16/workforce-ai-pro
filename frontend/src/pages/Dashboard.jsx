import { useState } from "react";
import { CheckCircle2, Clock, LogIn, LogOut } from "lucide-react";
import { attendanceApi, dashboardApi } from "../api/endpoints";
import { useApi, usePolling } from "../hooks/useApi";
import { Card, StatTile } from "../components/ui/Card";
import Badge from "../components/ui/Badge";
import { AsyncBoundary, EmptyState } from "../components/ui/States";
import { useAuth } from "../context/AuthContext";
import { percent, time, titleise } from "../utils/format";
import {
  Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import { RISK_COLOURS } from "../utils/format";

export default function Dashboard() {
  const { user } = useAuth();
  const summary = useApi(dashboardApi.summary, []);
  // Aggregate figures do not change second to second, so polling is the right
  // tool here. The WebSocket channel is reserved for genuinely live events.
  const live = usePolling(dashboardApi.live, 30000, []);
  const [action, setAction] = useState(null);

  const data = summary.data;
  const scope = data?.organisation || data?.team;
  const scopeLabel = data?.organisation ? "Organisation" : "My team";

  const punch = async (kind) => {
    setAction({ kind, busy: true });
    try {
      await (kind === "in" ? attendanceApi.checkIn() : attendanceApi.checkOut());
      await summary.refetch();
      setAction({ kind, message: kind === "in" ? "Checked in." : "Checked out." });
    } catch (error) {
      setAction({ kind, error: error.message });
    }
  };

  const riskData = data?.risk_distribution?.distribution
    ? Object.entries(data.risk_distribution.distribution).map(([name, value]) => ({
        name: titleise(name),
        value,
        colour: RISK_COLOURS[name] || "#94a3b8",
      }))
    : [];

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-xl font-semibold text-ink-900">
          Good to see you, {user?.full_name?.split(" ")[0]}
        </h1>
        <p className="mt-0.5 text-sm text-ink-500">
          {scopeLabel} view · updated {live.data ? time(live.data.as_of) : "—"}
        </p>
      </header>

      <AsyncBoundary
        loading={summary.loading}
        error={summary.error}
        onRetry={summary.refetch}
      >
        {data?.me && (
          <Card title="Today" subtitle={data.me.employee_code}>
            <div className="flex flex-wrap items-center gap-4">
              <div className="flex items-center gap-2 text-sm">
                <Clock className="h-4 w-4 text-ink-400" />
                <span className="text-ink-600">Status</span>
                <Badge status={data.me.todays_status || "absent"}>
                  {data.me.todays_status || "not marked"}
                </Badge>
              </div>

              {!data.me.checked_in_today && (
                <button className="btn-primary" onClick={() => punch("in")}>
                  <LogIn className="h-4 w-4" /> Check in
                </button>
              )}
              {data.me.checked_in_today && !data.me.checked_out_today && (
                <button className="btn-ghost" onClick={() => punch("out")}>
                  <LogOut className="h-4 w-4" /> Check out
                </button>
              )}
              {data.me.checked_out_today && (
                <span className="flex items-center gap-1.5 text-sm text-emerald-600">
                  <CheckCircle2 className="h-4 w-4" /> Day complete
                </span>
              )}

              {action?.message && (
                <span className="text-sm text-emerald-600">{action.message}</span>
              )}
              {action?.error && (
                <span className="text-sm text-red-600">{action.error}</span>
              )}
            </div>

            <dl className="mt-4 grid grid-cols-2 gap-4 border-t border-ink-100 pt-4 sm:grid-cols-4">
              {[
                ["Department", data.me.department || "—"],
                ["Designation", data.me.designation || "—"],
                ["Tenure", data.me.tenure_months ? `${data.me.tenure_months} months` : "—"],
                ["Pending leave", data.me.pending_leave_requests],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt className="text-xs text-ink-500">{label}</dt>
                  <dd className="mt-0.5 text-sm font-medium text-ink-800">{value}</dd>
                </div>
              ))}
            </dl>
          </Card>
        )}

        {scope && (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatTile label="Headcount" value={scope.headcount} />
            <StatTile
              label="Present today"
              value={scope.present_today}
              hint={percent(scope.attendance_percent)}
            />
            <StatTile label="On leave" value={scope.on_leave_today} />
            <StatTile
              label="At risk"
              value={scope.employees_at_risk}
              accent={scope.employees_at_risk > 0 ? "text-orange-600" : "text-ink-900"}
              hint="High or critical"
            />
          </div>
        )}

        <div className="grid gap-4 lg:grid-cols-2">
          {riskData.length > 0 && (
            <Card title="Risk distribution" subtitle="Active employees by band">
              <ResponsiveContainer width="100%" height={240}>
                <PieChart>
                  <Pie
                    data={riskData}
                    dataKey="value"
                    nameKey="name"
                    innerRadius={55}
                    outerRadius={90}
                    paddingAngle={2}
                  >
                    {riskData.map((entry) => (
                      <Cell key={entry.name} fill={entry.colour} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
              <div className="mt-2 flex flex-wrap justify-center gap-3">
                {riskData.map((entry) => (
                  <span key={entry.name} className="flex items-center gap-1.5 text-xs">
                    <span
                      className="h-2.5 w-2.5 rounded-full"
                      style={{ background: entry.colour }}
                    />
                    {entry.name} · {entry.value}
                  </span>
                ))}
              </div>
            </Card>
          )}

          <Card title="Right now" subtitle="Polled every 30 seconds">
            <AsyncBoundary loading={live.loading} error={live.error}>
              {live.data && (
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart
                    data={[
                      { name: "Working", value: live.data.currently_working },
                      { name: "Finished", value: live.data.completed_today },
                      { name: "On leave", value: live.data.on_leave_today },
                      { name: "Not in", value: live.data.not_yet_checked_in },
                    ]}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                    <XAxis dataKey="name" tick={{ fontSize: 12, fill: "#64748b" }} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 12, fill: "#64748b" }} />
                    <Tooltip />
                    <Bar dataKey="value" fill="#6366f1" radius={[6, 6, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </AsyncBoundary>
          </Card>
        </div>

        {!data?.me && !scope && (
          <EmptyState
            title="Nothing to show yet"
            hint="No employee profile is linked to this account, so there is no personal section."
          />
        )}
      </AsyncBoundary>
    </div>
  );
}
