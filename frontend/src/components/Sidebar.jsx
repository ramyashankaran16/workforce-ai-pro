import { NavLink } from "react-router-dom";
import { Sparkles } from "lucide-react";
import { NAV_ITEMS } from "../config/nav";
import { useAuth } from "../context/AuthContext";

export default function Sidebar({ open, onClose }) {
  const { can, canAny, user } = useAuth();

  const visible = NAV_ITEMS.filter((item) => {
    if (item.permission) return can(item.permission);
    if (item.permissionAny) return canAny(...item.permissionAny);
    return true;
  });

  return (
    <>
      {open && (
        <div
          className="fixed inset-0 z-20 bg-ink-900/40 lg:hidden"
          onClick={onClose}
          aria-hidden
        />
      )}
      <aside
        className={`fixed inset-y-0 left-0 z-30 flex w-64 flex-col border-r
                    border-ink-200 bg-white transition-transform lg:static
                    lg:translate-x-0 ${open ? "translate-x-0" : "-translate-x-full"}`}
      >
        <div className="flex items-center gap-2.5 border-b border-ink-100 px-5 py-4">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand-600">
            <Sparkles className="h-4 w-4 text-white" />
          </span>
          <div>
            <p className="text-sm font-semibold leading-tight text-ink-900">
              WorkForce AI
            </p>
            <p className="text-[11px] leading-tight text-ink-500">
              Attrition Intelligence
            </p>
          </div>
        </div>

        <nav className="flex-1 space-y-0.5 overflow-y-auto p-3">
          {visible.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              onClick={onClose}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
                  isActive
                    ? "bg-brand-50 font-medium text-brand-700"
                    : "text-ink-600 hover:bg-ink-50"
                }`
              }
            >
              <Icon className="h-4 w-4 shrink-0" />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-ink-100 px-5 py-3">
          <p className="text-[11px] text-ink-400">
            Signed in as {user?.role?.display_name ?? "—"}
          </p>
        </div>
      </aside>
    </>
  );
}
