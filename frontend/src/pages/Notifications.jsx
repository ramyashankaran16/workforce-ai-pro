import { notificationApi } from "../api/endpoints";
import { useApi } from "../hooks/useApi";
import Badge from "../components/ui/Badge";
import { AsyncBoundary, EmptyState } from "../components/ui/States";
import { shortDate, time } from "../utils/format";

export default function Notifications() {
  const feed = useApi(() => notificationApi.list({ size: 30 }), []);

  const markAll = async () => {
    await notificationApi.markAllRead().catch(() => {});
    feed.refetch().catch(() => {});
  };

  return (
    <div className="space-y-5">
      <header className="flex items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-ink-900">Notifications</h1>
          <p className="mt-0.5 text-sm text-ink-500">Unread first.</p>
        </div>
        <button className="btn-ghost" onClick={markAll}>
          Mark all read
        </button>
      </header>

      <div className="card divide-y divide-ink-100">
        <AsyncBoundary
          loading={feed.loading}
          error={feed.error}
          onRetry={feed.refetch}
          isEmpty={feed.data?.items?.length === 0}
          empty={<EmptyState title="Nothing to read" />}
        >
          {(feed.data?.items ?? []).map((item) => (
            <article
              key={item.id}
              className={`flex items-start gap-3 px-5 py-4 ${
                item.is_read ? "" : "bg-brand-50/40"
              }`}
            >
              {!item.is_read && (
                <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-brand-500" />
              )}
              <div className={`min-w-0 flex-1 ${item.is_read ? "pl-5" : ""}`}>
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-sm font-medium text-ink-800">{item.title}</p>
                  <Badge>{item.category}</Badge>
                  {item.priority !== "medium" && (
                    <Badge
                      tone={item.priority === "critical" ? "red" : "amber"}
                    >
                      {item.priority}
                    </Badge>
                  )}
                </div>
                <p className="mt-1 text-sm text-ink-600">{item.message}</p>
                <p className="mt-1 text-xs text-ink-400">
                  {shortDate(item.created_at)} · {time(item.created_at)}
                </p>
              </div>
            </article>
          ))}
        </AsyncBoundary>
      </div>
    </div>
  );
}
