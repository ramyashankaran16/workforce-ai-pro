const TONES = {
  neutral: "bg-ink-100 text-ink-700",
  brand: "bg-brand-50 text-brand-700",
  green: "bg-emerald-50 text-emerald-700",
  amber: "bg-amber-50 text-amber-700",
  orange: "bg-orange-50 text-orange-700",
  red: "bg-red-50 text-red-700",
};

const RISK_TONE = {
  low: "green",
  medium: "amber",
  high: "orange",
  critical: "red",
};

const STATUS_TONE = {
  active: "green", approved: "green", verified: "green", completed: "green",
  paid: "green", present: "green", deployed: "green", trained: "brand",
  pending: "amber", processing: "amber", draft: "neutral", late: "amber",
  self_review: "amber", manager_review: "amber", hr_review: "amber",
  rejected: "red", failed: "red", absent: "red", resigned: "red",
  terminated: "red", cancelled: "neutral", inactive: "neutral",
};

export default function Badge({ children, tone, risk, status, className = "" }) {
  const resolved =
    tone ||
    (risk && RISK_TONE[String(risk).toLowerCase()]) ||
    (status && STATUS_TONE[String(status).toLowerCase()]) ||
    "neutral";

  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs
                  font-medium capitalize ${TONES[resolved]} ${className}`}
    >
      {String(children ?? "").replace(/_/g, " ")}
    </span>
  );
}
