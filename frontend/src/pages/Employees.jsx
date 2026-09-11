import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { departmentApi, employeeApi } from "../api/endpoints";
import { useApi } from "../hooks/useApi";
import { Card } from "../components/ui/Card";
import Badge from "../components/ui/Badge";
import { Pagination, Table } from "../components/ui/Table";
import { AsyncBoundary, EmptyState } from "../components/ui/States";
import { useAuth } from "../context/AuthContext";
import { shortDate } from "../utils/format";

export default function Employees() {
  const navigate = useNavigate();
  const { role } = useAuth();
  const [filters, setFilters] = useState({ search: "", department_id: "", status: "" });
  const [page, setPage] = useState(1);

  const departments = useApi(() => departmentApi.list({ size: 100 }), []);
  const employees = useApi(
    () =>
      employeeApi.list({
        page,
        size: 15,
        ...Object.fromEntries(Object.entries(filters).filter(([, v]) => v !== "")),
      }),
    [page]
  );

  // Debounce the filter changes so typing does not fire a request per keystroke.
  useEffect(() => {
    const timer = setTimeout(() => {
      setPage(1);
      employees.refetch().catch(() => {});
    }, 350);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters.search, filters.department_id, filters.status]);

  const columns = [
    {
      key: "employee_code",
      header: "Code",
      className: "font-mono text-xs text-ink-500",
    },
    {
      key: "full_name",
      header: "Name",
      render: (row) => (
        <div>
          <p className="font-medium text-ink-800">{row.full_name}</p>
          <p className="text-xs text-ink-500">{row.work_email}</p>
        </div>
      ),
    },
    {
      key: "employment_type",
      header: "Type",
      render: (row) => <Badge>{row.employment_type}</Badge>,
    },
    {
      key: "work_mode",
      header: "Mode",
      render: (row) => <span className="capitalize text-ink-600">{row.work_mode}</span>,
    },
    {
      key: "status",
      header: "Status",
      render: (row) => <Badge status={row.status}>{row.status}</Badge>,
    },
    {
      key: "date_of_joining",
      header: "Joined",
      render: (row) => (
        <span className="text-ink-600">{shortDate(row.date_of_joining)}</span>
      ),
    },
  ];

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-ink-900">Employees</h1>
          <p className="mt-0.5 text-sm text-ink-500">
            {role === "manager"
              ? "Your direct reportees."
              : "Everyone on the books."}
          </p>
        </div>
      </header>

      <Card className="overflow-hidden">
        <div className="grid gap-3 sm:grid-cols-3">
          <input
            className="field"
            placeholder="Search name, code or email"
            value={filters.search}
            onChange={(event) =>
              setFilters((f) => ({ ...f, search: event.target.value }))
            }
          />
          <select
            className="field"
            value={filters.department_id}
            onChange={(event) =>
              setFilters((f) => ({ ...f, department_id: event.target.value }))
            }
          >
            <option value="">All departments</option>
            {(departments.data?.items ?? []).map((dept) => (
              <option key={dept.id} value={dept.id}>
                {dept.name}
              </option>
            ))}
          </select>
          <select
            className="field"
            value={filters.status}
            onChange={(event) =>
              setFilters((f) => ({ ...f, status: event.target.value }))
            }
          >
            <option value="">Any status</option>
            {["active", "on_leave", "notice_period", "resigned", "terminated"].map(
              (value) => (
                <option key={value} value={value}>
                  {value.replace(/_/g, " ")}
                </option>
              )
            )}
          </select>
        </div>
      </Card>

      <div className="card overflow-hidden">
        <AsyncBoundary
          loading={employees.loading}
          error={employees.error}
          onRetry={employees.refetch}
          isEmpty={employees.data?.items?.length === 0}
          empty={
            <EmptyState
              title="No employees match"
              hint="Try clearing the filters, or widen the search term."
            />
          }
        >
          <Table
            columns={columns}
            rows={employees.data?.items ?? []}
            onRowClick={(row) => navigate(`/employees/${row.id}`)}
          />
          <Pagination meta={employees.data?.meta} onChange={setPage} />
        </AsyncBoundary>
      </div>
    </div>
  );
}
