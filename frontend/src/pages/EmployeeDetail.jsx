import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Sparkles, TrendingDown, TrendingUp } from "lucide-react";
import { employeeApi, predictionApi, riskApi } from "../api/endpoints";
import { useApi } from "../hooks/useApi";
import { Card } from "../components/ui/Card";
import Badge from "../components/ui/Badge";
import { AsyncBoundary, EmptyState } from "../components/ui/States";
import { useAuth } from "../context/AuthContext";
import { currency, percent, RISK_COLOURS, shortDate, titleise } from "../utils/format";

export default function EmployeeDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { can } = useAuth();

  const employee = useApi(() => employeeApi.get(id), [id]);
  const history = useApi(() => employeeApi.history(id), [id]);
  const risk = useApi(() => riskApi.employee(id), [id], { immediate: false });

  const [prediction, setPrediction] = useState(null);
  const [predicting, setPredicting] = useState(false);
  const [predictError, setPredictError] = useState(null);

  const runPrediction = async () => {
    setPredicting(true);
    setPredictError(null);
    try {
      setPrediction(await predictionApi.predict(id));
      risk.refetch().catch(() => {});
    } catch (error) {
      setPredictError(error.message);
    } finally {
      setPredicting(false);
    }
  };

  const person = employee.data;

  return (
    <div className="space-y-5">
      <button
        onClick={() => navigate(-1)}
        className="flex items-center gap-1.5 text-sm text-ink-500 hover:text-ink-800"
      >
        <ArrowLeft className="h-4 w-4" /> Back
      </button>

      <AsyncBoundary
        loading={employee.loading}
        error={employee.error}
        onRetry={employee.refetch}
      >
        {person && (
          <>
            <div className="card p-5">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <h1 className="text-xl font-semibold text-ink-900">
                    {person.full_name}
                  </h1>
                  <p className="mt-0.5 text-sm text-ink-500">
                    {person.employee_code} · {person.work_email}
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Badge status={person.status}>{person.status}</Badge>
                    <Badge>{person.employment_type}</Badge>
                    <Badge>{person.work_mode}</Badge>
                    {person.current_risk_level && (
                      <Badge risk={person.current_risk_level}>
                        {person.current_risk_level} risk
                      </Badge>
                    )}
                  </div>
                </div>

                {can("prediction:run") && (
                  <button
                    className="btn-primary"
                    onClick={runPrediction}
                    disabled={predicting}
                  >
                    <Sparkles className="h-4 w-4" />
                    {predicting ? "Scoring" : "Score attrition risk"}
                  </button>
                )}
              </div>

              <dl className="mt-5 grid grid-cols-2 gap-4 border-t border-ink-100 pt-4 lg:grid-cols-4">
                {[
                  ["Department", person.department_name],
                  ["Designation", person.designation_title],
                  ["Manager", person.manager_name],
                  ["Reportees", person.reportee_count],
                  ["Joined", shortDate(person.date_of_joining)],
                  ["Tenure", person.tenure_months ? `${person.tenure_months} months` : null],
                  ["Salary", person.current_salary ? currency(person.current_salary) : null],
                  [
                    "Performance",
                    person.last_performance_rating
                      ? `${person.last_performance_rating}/5`
                      : null,
                  ],
                ].map(([label, value]) => (
                  <div key={label}>
                    <dt className="text-xs text-ink-500">{label}</dt>
                    <dd className="mt-0.5 text-sm font-medium text-ink-800">
                      {value ?? "—"}
                    </dd>
                  </div>
                ))}
              </dl>
            </div>

            {predictError && (
              <div className="rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-800">
                {predictError}
              </div>
            )}

            {prediction && <PredictionPanel prediction={prediction} />}

            <div className="grid gap-4 lg:grid-cols-2">
              <Card title="Change history" subtitle="Written automatically on every material change">
                <AsyncBoundary
                  loading={history.loading}
                  error={history.error}
                  isEmpty={history.data?.length === 0}
                  empty={<EmptyState title="No recorded changes" />}
                >
                  <ol className="space-y-3">
                    {(history.data ?? []).map((entry) => (
                      <li key={entry.id} className="flex gap-3">
                        <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-brand-500" />
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-ink-800">
                            {titleise(entry.event_type)}
                          </p>
                          <p className="text-xs text-ink-500">
                            {shortDate(entry.effective_date)}
                            {entry.field_name && ` · ${entry.field_name}`}
                            {entry.old_value && ` · ${entry.old_value} → ${entry.new_value}`}
                          </p>
                          {entry.remarks && (
                            <p className="mt-0.5 text-xs text-ink-500">{entry.remarks}</p>
                          )}
                        </div>
                      </li>
                    ))}
                  </ol>
                </AsyncBoundary>
              </Card>

              <Card
                title="Composite risk score"
                subtitle="Model probability blended with behavioural signals"
                action={
                  <button className="btn-ghost px-2.5 py-1 text-xs" onClick={risk.refetch}>
                    Load
                  </button>
                }
              >
                {!risk.data && !risk.loading && (
                  <EmptyState
                    title="Not scored yet"
                    hint="Select Load, or run a risk evaluation from the Risk Monitor."
                  />
                )}
                <AsyncBoundary loading={risk.loading} error={risk.error}>
                  {risk.data && <RiskBreakdown score={risk.data} />}
                </AsyncBoundary>
              </Card>
            </div>
          </>
        )}
      </AsyncBoundary>
    </div>
  );
}

function PredictionPanel({ prediction }) {
  const probability = prediction.attrition_probability;
  const colour = RISK_COLOURS[prediction.risk_level] || "#64748b";

  return (
    <Card
      title="Attrition prediction"
      subtitle="Factors measured by re-scoring with each value replaced by the population typical"
    >
      <div className="flex flex-wrap items-center gap-6">
        <div className="flex items-baseline gap-2">
          <span className="text-4xl font-semibold tabular-nums" style={{ color: colour }}>
            {(probability * 100).toFixed(0)}%
          </span>
          <Badge risk={prediction.risk_level}>{prediction.risk_level}</Badge>
        </div>
        <div className="text-sm text-ink-600">
          <p>{prediction.will_leave ? "Flagged as likely to leave" : "Not flagged"}</p>
          <p className="text-xs text-ink-500">
            Confidence {percent((prediction.confidence ?? 0) * 100, 0)}
          </p>
        </div>
      </div>

      {prediction.explanation && (
        <p className="mt-4 rounded-lg bg-ink-50 px-4 py-3 text-sm leading-relaxed text-ink-700">
          {prediction.explanation}
        </p>
      )}

      {prediction.factors?.length > 0 && (
        <ul className="mt-4 space-y-2.5">
          {prediction.factors.map((factor) => {
            const raises = factor.contribution > 0;
            const width = Math.min(Math.abs(factor.contribution) * 400, 100);
            return (
              <li key={factor.feature} className="flex items-center gap-3">
                {raises ? (
                  <TrendingUp className="h-4 w-4 shrink-0 text-red-500" />
                ) : (
                  <TrendingDown className="h-4 w-4 shrink-0 text-emerald-500" />
                )}
                <div className="min-w-0 flex-1">
                  <div className="flex justify-between gap-3 text-sm">
                    <span className="truncate text-ink-800">{factor.label}</span>
                    <span className="shrink-0 text-xs text-ink-500">
                      {factor.employee_value ?? "—"}
                      {factor.population_typical &&
                        ` vs ${factor.population_typical} typical`}
                    </span>
                  </div>
                  <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-ink-100">
                    <div
                      className={`h-full rounded-full ${
                        raises ? "bg-red-400" : "bg-emerald-400"
                      }`}
                      style={{ width: `${width}%` }}
                    />
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

function RiskBreakdown({ score }) {
  const components = [
    ["ML probability", score.ml_probability_score],
    ["Compensation", score.compensation_score],
    ["Engagement", score.engagement_score],
    ["Workload", score.workload_score],
    ["Attendance", score.attendance_score],
    ["Performance", score.performance_score],
    ["Tenure", score.tenure_score],
    ["Leave pattern", score.leave_pattern_score],
  ].filter(([, value]) => value !== null && value !== undefined);

  return (
    <div>
      <div className="flex items-baseline gap-3">
        <span className="text-3xl font-semibold tabular-nums text-ink-900">
          {score.overall_score.toFixed(0)}
          <span className="text-base text-ink-400">/100</span>
        </span>
        <Badge risk={score.risk_level}>{score.risk_level}</Badge>
        <Badge>{score.trend}</Badge>
      </div>

      {score.summary && <p className="mt-3 text-sm text-ink-600">{score.summary}</p>}

      <ul className="mt-4 space-y-2">
        {components.map(([label, value]) => (
          <li key={label}>
            <div className="flex justify-between text-xs">
              <span className="text-ink-600">{label}</span>
              <span className="tabular-nums text-ink-500">{value.toFixed(0)}</span>
            </div>
            <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-ink-100">
              <div
                className="h-full rounded-full bg-brand-500"
                style={{ width: `${value}%` }}
              />
            </div>
          </li>
        ))}
      </ul>

      {score.breakdown?.ml_available === false && (
        <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
          No model is deployed, so the ML weight has been redistributed across
          the remaining components rather than scored as zero.
        </p>
      )}
    </div>
  );
}
