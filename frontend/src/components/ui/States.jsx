import { AlertCircle, Inbox, Loader2 } from "lucide-react";

export function Spinner({ label = "Loading" }) {
  return (
    <div className="flex items-center justify-center gap-2 py-10 text-sm text-ink-500">
      <Loader2 className="h-4 w-4 animate-spin" />
      {label}
    </div>
  );
}

export function ErrorState({ error, onRetry }) {
  return (
    <div className="flex flex-col items-center gap-3 py-10 text-center">
      <AlertCircle className="h-6 w-6 text-red-500" />
      <p className="max-w-md text-sm text-ink-600">
        {error?.message || "Something went wrong."}
      </p>
      {onRetry && (
        <button className="btn-ghost" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title = "Nothing here yet", hint, action }) {
  return (
    <div className="flex flex-col items-center gap-2 py-10 text-center">
      <Inbox className="h-6 w-6 text-ink-300" />
      <p className="text-sm font-medium text-ink-700">{title}</p>
      {hint && <p className="max-w-md text-xs text-ink-500">{hint}</p>}
      {action}
    </div>
  );
}

/** Wraps the loading / error / empty branches so pages do not repeat them. */
export function AsyncBoundary({ loading, error, onRetry, isEmpty, empty, children }) {
  if (loading) return <Spinner />;
  if (error) return <ErrorState error={error} onRetry={onRetry} />;
  if (isEmpty) return empty ?? <EmptyState />;
  return children;
}
