export function Card({ title, subtitle, action, children, className = "" }) {
  return (
    <section className={`card ${className}`}>
      {(title || action) && (
        <header className="flex items-start justify-between gap-4 border-b border-ink-100 px-5 py-4">
          <div>
            {title && <h2 className="text-sm font-semibold text-ink-800">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-ink-500">{subtitle}</p>}
          </div>
          {action}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

export function StatTile({ label, value, hint, accent = "text-ink-900" }) {
  return (
    <div className="card p-5">
      <p className="text-xs font-medium uppercase tracking-wide text-ink-500">{label}</p>
      <p className={`mt-2 text-2xl font-semibold tabular-nums ${accent}`}>{value}</p>
      {hint && <p className="mt-1 text-xs text-ink-500">{hint}</p>}
    </div>
  );
}
