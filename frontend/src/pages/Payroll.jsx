import client from "../api/client";
import { useApi } from "../hooks/useApi";
import { Card } from "../components/ui/Card";
import Badge from "../components/ui/Badge";
import { Table } from "../components/ui/Table";
import { AsyncBoundary, EmptyState } from "../components/ui/States";
import { currency } from "../utils/format";

const payslipApi = {
  mine: () => client.get("/payroll/payslips/me", { params: { size: 24 } }).then((r) => r.data),
};

export default function Payroll() {
  const payslips = useApi(payslipApi.mine, []);

  const download = (id, slip) => {
    // The PDF route is permission-checked server side, so the token must travel
    // with the request rather than the browser opening the URL directly.
    client
      .get(`/payroll/payslips/${id}/pdf`, { responseType: "blob" })
      .then(({ data }) => {
        const url = URL.createObjectURL(data);
        const link = document.createElement("a");
        link.href = url;
        link.download = `${slip}.pdf`;
        link.click();
        URL.revokeObjectURL(url);
      })
      .catch(() => {});
  };

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-xl font-semibold text-ink-900">Payroll</h1>
        <p className="mt-0.5 text-sm text-ink-500">
          Your payslips. Amounts are computed with Decimal arithmetic and
          rounded half-up at each step.
        </p>
      </header>

      <div className="card overflow-hidden">
        <AsyncBoundary
          loading={payslips.loading}
          error={payslips.error}
          onRetry={payslips.refetch}
          isEmpty={payslips.data?.items?.length === 0}
          empty={
            <EmptyState
              title="No payslips yet"
              hint="They appear once HR processes a payroll run for a period you worked."
            />
          }
        >
          <Table
            columns={[
              { key: "slip_number", header: "Slip", className: "font-mono text-xs" },
              {
                key: "present_days",
                header: "Days",
                render: (row) => `${row.present_days} / ${row.working_days}`,
              },
              {
                key: "gross_earnings",
                header: "Gross",
                render: (row) => currency(row.gross_earnings),
              },
              {
                key: "total_deductions",
                header: "Deductions",
                render: (row) => (
                  <span className="text-red-600">-{currency(row.total_deductions)}</span>
                ),
              },
              {
                key: "net_pay",
                header: "Net",
                render: (row) => (
                  <span className="font-semibold">{currency(row.net_pay)}</span>
                ),
              },
              {
                key: "status",
                header: "Status",
                render: (row) => <Badge status={row.status}>{row.status}</Badge>,
              },
              {
                key: "download",
                header: "",
                render: (row) => (
                  <button
                    className="btn-ghost px-2.5 py-1 text-xs"
                    onClick={() => download(row.id, row.slip_number)}
                  >
                    PDF
                  </button>
                ),
              },
            ]}
            rows={payslips.data?.items ?? []}
          />
        </AsyncBoundary>
      </div>
    </div>
  );
}
