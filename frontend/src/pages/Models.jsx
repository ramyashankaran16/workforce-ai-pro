import { useState } from "react";
import { PlayCircle, Rocket } from "lucide-react";
import { predictionApi } from "../api/endpoints";
import { useApi } from "../hooks/useApi";
import { Card, StatTile } from "../components/ui/Card";
import Badge from "../components/ui/Badge";
import { Table } from "../components/ui/Table";
import { AsyncBoundary, EmptyState } from "../components/ui/States";
import { useAuth } from "../context/AuthContext";
import {
  Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";

const axis = { fontSize: 12, fill: "#64748b" };

export default function Models() {
  const { can } = useAuth();
  const models = useApi(() => predictionApi.models({ size: 20 }), []);
  const active = useApi(predictionApi.activeModel, []);
  const [busy, setBusy] = useState(null);
  const [message, setMessage] = useState(null);

  const deploy = async (id) => {
    setBusy(id);
    setMessage(null);
    try {
      await predictionApi.deploy(id);
      setMessage("Deployed. The previous version has been archived.");
      models.refetch().catch(() => {});
      active.refetch().catch(() => {});
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy(null);
    }
  };

  const runBatch = async () => {
    setBusy("batch");
    setMessage(null);
    try {
      const result = await predictionApi.batch();
      setMessage(
        `Scored ${result.total_records} employees in ${result.duration_seconds}s — ` +
          `${result.high_risk_count} high risk.`
      );
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy(null);
    }
  };

  const evaluation = active.data?.hyperparameters?.evaluation;

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-ink-900">AI models</h1>
          <p className="mt-0.5 text-sm text-ink-500">
            Exactly one version is active at a time. Every artifact stores its
            own feature list and threshold, so an old prediction can still be
            explained.
          </p>
        </div>
        {can("prediction:run") && active.data && (
          <button className="btn-primary" onClick={runBatch} disabled={busy === "batch"}>
            <PlayCircle className="h-4 w-4" />
            {busy === "batch" ? "Scoring" : "Score everyone"}
          </button>
        )}
      </header>

      {message && (
        <div className="rounded-lg bg-brand-50 px-4 py-3 text-sm text-brand-700">
          {message}
        </div>
      )}

      <AsyncBoundary loading={active.loading} error={active.error}>
        {!active.data ? (
          <EmptyState
            title="No model deployed"
            hint="Train one from the API, then deploy it here. Risk scores fall back to behavioural signals until then."
          />
        ) : (
          <>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <StatTile
                label="Precision"
                value={evaluation?.precision ?? "—"}
                hint="Of those flagged, how many were right"
              />
              <StatTile
                label="Recall"
                value={evaluation?.recall ?? "—"}
                hint="Of those who left, how many we caught"
              />
              <StatTile
                label="PR-AUC"
                value={evaluation?.pr_auc ?? "—"}
                hint="The honest summary for imbalanced data"
              />
              <StatTile
                label="Accuracy"
                value={evaluation?.accuracy ?? "—"}
                hint={`Majority baseline ${
                  evaluation?.majority_class_baseline_accuracy ?? "—"
                }`}
              />
            </div>

            {evaluation?.majority_class_baseline_accuracy && (
              <p className="rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-800">
                Accuracy is shown next to the majority-class baseline on purpose.
                A model predicting that nobody leaves would score{" "}
                {evaluation.majority_class_baseline_accuracy}. The gap is what
                the model is actually worth.
              </p>
            )}

            {evaluation?.threshold_sweep && (
              <Card
                title="Precision and recall by threshold"
                subtitle="0.5 is arbitrary — a false positive costs a conversation, a false negative costs an employee"
              >
                <ResponsiveContainer width="100%" height={260}>
                  <LineChart data={evaluation.threshold_sweep}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                    <XAxis dataKey="threshold" tick={axis} />
                    <YAxis domain={[0, 1]} tick={axis} />
                    <Tooltip />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Line
                      type="monotone"
                      dataKey="precision"
                      name="Precision"
                      stroke="#6366f1"
                      strokeWidth={2}
                    />
                    <Line
                      type="monotone"
                      dataKey="recall"
                      name="Recall"
                      stroke="#f59e0b"
                      strokeWidth={2}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </Card>
            )}

            {active.data.feature_importance && (
              <Card title="Feature importance" subtitle={`${active.data.name} v${active.data.version}`}>
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart
                    data={Object.entries(active.data.feature_importance)
                      .slice(0, 10)
                      .map(([feature, importance]) => ({ feature, importance }))}
                    layout="vertical"
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" horizontal={false} />
                    <XAxis type="number" tick={axis} />
                    <YAxis
                      type="category"
                      dataKey="feature"
                      tick={{ fontSize: 10, fill: "#64748b" }}
                      width={160}
                    />
                    <Tooltip />
                    <Bar dataKey="importance" fill="#6366f1" radius={[0, 6, 6, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </Card>
            )}
          </>
        )}
      </AsyncBoundary>

      <div className="card overflow-hidden">
        <header className="border-b border-ink-100 px-5 py-4">
          <h2 className="text-sm font-semibold text-ink-800">All versions</h2>
        </header>
        <AsyncBoundary
          loading={models.loading}
          error={models.error}
          isEmpty={models.data?.items?.length === 0}
          empty={<EmptyState title="No models trained yet" />}
        >
          <Table
            columns={[
              {
                key: "name",
                header: "Model",
                render: (row) => (
                  <div>
                    <p className="font-medium text-ink-800">{row.name}</p>
                    <p className="text-xs text-ink-500">
                      v{row.version} · {row.algorithm.replace(/_/g, " ")}
                    </p>
                  </div>
                ),
              },
              {
                key: "status",
                header: "Status",
                render: (row) => (
                  <div className="flex gap-1.5">
                    <Badge status={row.status}>{row.status}</Badge>
                    {row.is_active && <Badge tone="brand">active</Badge>}
                  </div>
                ),
              },
              {
                key: "f1_score",
                header: "F1",
                render: (row) => (
                  <span className="tabular-nums">{row.f1_score ?? "—"}</span>
                ),
              },
              {
                key: "roc_auc",
                header: "ROC-AUC",
                render: (row) => (
                  <span className="tabular-nums">{row.roc_auc ?? "—"}</span>
                ),
              },
              {
                key: "train_rows",
                header: "Rows",
                render: (row) =>
                  row.train_rows ? `${row.train_rows} / ${row.test_rows}` : "—",
              },
              {
                key: "actions",
                header: "",
                render: (row) =>
                  can("model:deploy") && !row.is_active && row.status !== "failed" ? (
                    <button
                      className="btn-ghost px-2.5 py-1 text-xs"
                      onClick={() => deploy(row.id)}
                      disabled={busy === row.id}
                    >
                      <Rocket className="h-3.5 w-3.5" /> Deploy
                    </button>
                  ) : null,
              },
            ]}
            rows={models.data?.items ?? []}
          />
        </AsyncBoundary>
      </div>
    </div>
  );
}
