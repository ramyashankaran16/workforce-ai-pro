import { useState } from "react";
import { attendanceApi } from "../api/endpoints";
import { useApi } from "../hooks/useApi";
import { Card } from "../components/ui/Card";
import Badge from "../components/ui/Badge";
import { Pagination, Table } from "../components/ui/Table";
import { AsyncBoundary, EmptyState } from "../components/ui/States";
import { useAuth } from "../context/AuthContext";
import { shortDate, time } from "../utils/format";

export default function Attendance() {
  const { canAny } = useAuth();
  const teamView = canAny("attendance:read_team", "attendance:read_all");
  const [tab, setTab] = useState("me");
  const [page, setPage] = useState(1);

  const records = useApi(
    () =>
      tab === "me"
        ? attendanceApi.mine({ page, size: 15 })
        : attendanceApi.list({ page, size: 15 }),
    [tab, page]
  );

  const columns = [
    {
      key: "attendance_date",
      header: "Date",
      render: (row) => shortDate(row.attendance_date),
    },
    ...(tab === "team"
      ? [{ key: "employee_id", header: "Employee", render: (row) => `#${row.employee_id}` }]
      : []),
    {
      key: "status",
      header: "Status",
      render: (row) => <Badge status={row.status}>{row.status}</Badge>,
    },
    { key: "check_in", header: "In", render: (row) => time(row.check_in) },
    { key: "check_out", header: "Out", render: (row) => time(row.check_out) },
    {
      key: "worked_hours",
      header: "Worked",
      render: (row) => <span className="tabular-nums">{row.worked_hours.toFixed(1)}h</span>,
    },
    {
      key: "overtime_hours",
      header: "Overtime",
      render: (row) =>
        row.overtime_hours > 0 ? (
          <span className="tabular-nums text-amber-600">
            +{row.overtime_hours.toFixed(1)}h
          </span>
        ) : (
          "—"
        ),
    },
    {
      key: "late_minutes",
      header: "Late",
      render: (row) =>
        row.late_minutes > 0 ? (
          <span className="text-red-600">{row.late_minutes} min</span>
        ) : (
          "—"
        ),
    },
  ];

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-xl font-semibold text-ink-900">Attendance</h1>
        <p className="mt-0.5 text-sm text-ink-500">
          Worked hours, overtime and lateness are derived from the timestamps
          and the assigned shift — never supplied by the client.
        </p>
      </header>

      {teamView && (
        <div className="flex gap-1 rounded-lg border border-ink-200 bg-white p-1">
          {[
            ["me", "My attendance"],
            ["team", "Team"],
          ].map(([value, label]) => (
            <button
              key={value}
              onClick={() => {
                setTab(value);
                setPage(1);
              }}
              className={`flex-1 rounded-md px-3 py-1.5 text-sm transition-colors ${
                tab === value
                  ? "bg-brand-50 font-medium text-brand-700"
                  : "text-ink-600 hover:bg-ink-50"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      <div className="card overflow-hidden">
        <AsyncBoundary
          loading={records.loading}
          error={records.error}
          onRetry={records.refetch}
          isEmpty={records.data?.items?.length === 0}
          empty={
            <EmptyState
              title="No attendance records"
              hint="Records appear once someone checks in, or after the nightly marking job runs."
            />
          }
        >
          <Table columns={columns} rows={records.data?.items ?? []} />
          <Pagination meta={records.data?.meta} onChange={setPage} />
        </AsyncBoundary>
      </div>
    </div>
  );
}
