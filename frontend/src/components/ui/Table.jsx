export function Table({ columns, rows, onRowClick, rowKey = (row, i) => row.id ?? i }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-ink-200">
            {columns.map((column) => (
              <th
                key={column.key}
                className={`whitespace-nowrap px-4 py-2.5 text-xs font-semibold
                            uppercase tracking-wide text-ink-500 ${column.className || ""}`}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr
              key={rowKey(row, index)}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              className={`border-b border-ink-100 last:border-0 ${
                onRowClick ? "cursor-pointer hover:bg-ink-50" : ""
              }`}
            >
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={`px-4 py-3 align-middle ${column.className || ""}`}
                >
                  {column.render ? column.render(row) : row[column.key] ?? "—"}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Pagination({ meta, onChange }) {
  if (!meta || meta.pages <= 1) return null;
  return (
    <div className="flex items-center justify-between border-t border-ink-100 px-4 py-3 text-sm">
      <p className="text-xs text-ink-500">
        Page {meta.page} of {meta.pages} · {meta.total} record
        {meta.total === 1 ? "" : "s"}
      </p>
      <div className="flex gap-2">
        <button
          className="btn-ghost px-2.5 py-1 text-xs"
          disabled={!meta.has_prev}
          onClick={() => onChange(meta.page - 1)}
        >
          Previous
        </button>
        <button
          className="btn-ghost px-2.5 py-1 text-xs"
          disabled={!meta.has_next}
          onClick={() => onChange(meta.page + 1)}
        >
          Next
        </button>
      </div>
    </div>
  );
}
