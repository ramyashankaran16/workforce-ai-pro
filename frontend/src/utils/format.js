export function initials(name = "") {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
}

export function currency(value) {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(Number(value));
}

export function percent(value, digits = 1) {
  if (value === null || value === undefined) return "—";
  return `${Number(value).toFixed(digits)}%`;
}

export function shortDate(value) {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export function time(value) {
  if (!value) return "—";
  return new Date(value).toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function titleise(value = "") {
  return String(value).replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export const RISK_COLOURS = {
  low: "#10b981",
  medium: "#f59e0b",
  high: "#f97316",
  critical: "#ef4444",
};

export const CHART_COLOURS = [
  "#6366f1", "#06b6d4", "#f59e0b", "#10b981",
  "#ef4444", "#8b5cf6", "#ec4899", "#14b8a6",
];
