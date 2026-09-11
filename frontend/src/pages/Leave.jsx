import { useState } from "react";
import { CalendarPlus, Check, X } from "lucide-react";
import { leaveApi } from "../api/endpoints";
import { useApi } from "../hooks/useApi";
import { Card } from "../components/ui/Card";
import Badge from "../components/ui/Badge";
import { Table } from "../components/ui/Table";
import { AsyncBoundary, EmptyState } from "../components/ui/States";
import { useAuth } from "../context/AuthContext";
import { shortDate } from "../utils/format";

export default function Leave() {
  const { can } = useAuth();
  const balances = useApi(() => leaveApi.balance(), []);
  const mine = useApi(() => leaveApi.mine({ size: 20 }), []);
  const types = useApi(leaveApi.types, []);
  const pending = useApi(
    () => leaveApi.pending({ size: 20 }),
    [],
    { immediate: can("leave:approve") }
  );

  const [form, setForm] = useState({
    leave_type_id: "",
    start_date: "",
    end_date: "",
    reason: "",
  });
  const [status, setStatus] = useState(null);

  const apply = async (event) => {
    event.preventDefault();
    setStatus({ busy: true });
    try {
      await leaveApi.apply({ ...form, leave_type_id: Number(form.leave_type_id) });
      setStatus({ message: "Request submitted." });
      setForm({ leave_type_id: "", start_date: "", end_date: "", reason: "" });
      balances.refetch().catch(() => {});
      mine.refetch().catch(() => {});
    } catch (error) {
      setStatus({ error: error.message });
    }
  };

  const decide = async (id, approve) => {
    try {
      await (approve ? leaveApi.approve(id, "") : leaveApi.reject(id, ""));
      pending.refetch().catch(() => {});
    } catch (error) {
      setStatus({ error: error.message });
    }
  };

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-xl font-semibold text-ink-900">Leave</h1>
        <p className="mt-0.5 text-sm text-ink-500">
          Weekends and public holidays inside a range are not charged. Days move
          to pending the moment you apply, so an overlapping request cannot also
          fit.
        </p>
      </header>

      <AsyncBoundary loading={balances.loading} error={balances.error}>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {(balances.data ?? []).map((balance) => (
            <div key={balance.id} className="card p-4">
              <div className="flex items-baseline justify-between">
                <p className="text-sm font-medium text-ink-800">
                  {balance.leave_type_name}
                </p>
                <span className="text-lg font-semibold tabular-nums text-ink-900">
                  {balance.available}
                </span>
              </div>
              <p className="mt-0.5 text-xs text-ink-500">
                {balance.used} used · {balance.pending} pending · {balance.allocated}{" "}
                allocated
              </p>
              <div className="mt-2 flex h-1.5 overflow-hidden rounded-full bg-ink-100">
                <div
                  className="bg-emerald-400"
                  style={{
                    width: `${(balance.used / Math.max(balance.allocated, 1)) * 100}%`,
                  }}
                />
                <div
                  className="bg-amber-300"
                  style={{
                    width: `${(balance.pending / Math.max(balance.allocated, 1)) * 100}%`,
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      </AsyncBoundary>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Apply for leave" className="lg:col-span-1">
          <form onSubmit={apply} className="space-y-3">
            <div>
              <label className="label">Type</label>
              <select
                className="field"
                required
                value={form.leave_type_id}
                onChange={(event) =>
                  setForm((f) => ({ ...f, leave_type_id: event.target.value }))
                }
              >
                <option value="">Select a type</option>
                {(types.data ?? []).map((type) => (
                  <option key={type.id} value={type.id}>
                    {type.name} {type.is_paid ? "" : "(unpaid)"}
                  </option>
                ))}
              </select>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label">From</label>
                <input
                  type="date"
                  required
                  className="field"
                  value={form.start_date}
                  onChange={(event) =>
                    setForm((f) => ({ ...f, start_date: event.target.value }))
                  }
                />
              </div>
              <div>
                <label className="label">To</label>
                <input
                  type="date"
                  required
                  className="field"
                  value={form.end_date}
                  onChange={(event) =>
                    setForm((f) => ({ ...f, end_date: event.target.value }))
                  }
                />
              </div>
            </div>

            <div>
              <label className="label">Reason</label>
              <textarea
                required
                minLength={5}
                rows={3}
                className="field"
                placeholder="Family function at home"
                value={form.reason}
                onChange={(event) =>
                  setForm((f) => ({ ...f, reason: event.target.value }))
                }
              />
            </div>

            {status?.error && (
              <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
                {status.error}
              </p>
            )}
            {status?.message && (
              <p className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
                {status.message}
              </p>
            )}

            <button className="btn-primary w-full" type="submit">
              <CalendarPlus className="h-4 w-4" /> Submit request
            </button>
          </form>
        </Card>

        <div className="space-y-4 lg:col-span-2">
          {can("leave:approve") && (
            <Card title="Awaiting your approval">
              <AsyncBoundary
                loading={pending.loading}
                error={pending.error}
                isEmpty={pending.data?.items?.length === 0}
                empty={<EmptyState title="Nothing waiting on you" />}
              >
                <ul className="space-y-2.5">
                  {(pending.data?.items ?? []).map((request) => (
                    <li
                      key={request.id}
                      className="flex items-start justify-between gap-3 rounded-lg border border-ink-200 px-4 py-3"
                    >
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-ink-800">
                          Employee #{request.employee_id} · {request.total_days} day
                          {request.total_days === 1 ? "" : "s"}
                        </p>
                        <p className="text-xs text-ink-500">
                          {shortDate(request.start_date)} – {shortDate(request.end_date)}
                        </p>
                        <p className="mt-1 text-xs text-ink-600">{request.reason}</p>
                      </div>
                      <div className="flex shrink-0 gap-2">
                        <button
                          className="btn-ghost px-2 py-1"
                          onClick={() => decide(request.id, true)}
                        >
                          <Check className="h-4 w-4 text-emerald-600" />
                        </button>
                        <button
                          className="btn-ghost px-2 py-1"
                          onClick={() => decide(request.id, false)}
                        >
                          <X className="h-4 w-4 text-red-600" />
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              </AsyncBoundary>
            </Card>
          )}

          <div className="card overflow-hidden">
            <header className="border-b border-ink-100 px-5 py-4">
              <h2 className="text-sm font-semibold text-ink-800">My requests</h2>
            </header>
            <AsyncBoundary
              loading={mine.loading}
              error={mine.error}
              isEmpty={mine.data?.items?.length === 0}
              empty={<EmptyState title="No requests yet" />}
            >
              <Table
                columns={[
                  {
                    key: "start_date",
                    header: "Dates",
                    render: (row) =>
                      `${shortDate(row.start_date)} – ${shortDate(row.end_date)}`,
                  },
                  {
                    key: "total_days",
                    header: "Days",
                    render: (row) => <span className="tabular-nums">{row.total_days}</span>,
                  },
                  {
                    key: "status",
                    header: "Status",
                    render: (row) => <Badge status={row.status}>{row.status}</Badge>,
                  },
                  {
                    key: "reason",
                    header: "Reason",
                    render: (row) => (
                      <span className="line-clamp-1 text-xs text-ink-600">
                        {row.reason}
                      </span>
                    ),
                  },
                ]}
                rows={mine.data?.items ?? []}
              />
            </AsyncBoundary>
          </div>
        </div>
      </div>
    </div>
  );
}
