import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bell, LogOut, Menu, Search } from "lucide-react";
import { notificationApi, searchApi } from "../api/endpoints";
import { useAuth } from "../context/AuthContext";
import { initials } from "../utils/format";

export default function Topbar({ onMenu }) {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const [unread, setUnread] = useState(0);
  const [term, setTerm] = useState("");
  const [results, setResults] = useState([]);
  const boxRef = useRef(null);

  useEffect(() => {
    notificationApi
      .count()
      .then((data) => setUnread(data.unread))
      .catch(() => {});
  }, []);

  // Debounced so typing does not fire a request per keystroke.
  useEffect(() => {
    if (term.trim().length < 2) {
      setResults([]);
      return;
    }
    const timer = setTimeout(() => {
      searchApi
        .global(term.trim())
        .then((data) => setResults(data.results.slice(0, 6)))
        .catch(() => setResults([]));
    }, 300);
    return () => clearTimeout(timer);
  }, [term]);

  useEffect(() => {
    const close = (event) => {
      if (boxRef.current && !boxRef.current.contains(event.target)) setResults([]);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const openResult = (result) => {
    setTerm("");
    setResults([]);
    if (result.type === "employee") navigate(`/employees/${result.id}`);
  };

  return (
    <header className="sticky top-0 z-10 flex items-center gap-3 border-b border-ink-200 bg-white/90 px-4 py-3 backdrop-blur">
      <button className="rounded-lg p-2 hover:bg-ink-50 lg:hidden" onClick={onMenu}>
        <Menu className="h-5 w-5 text-ink-600" />
      </button>

      <div className="relative max-w-md flex-1" ref={boxRef}>
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-400" />
        <input
          value={term}
          onChange={(event) => setTerm(event.target.value)}
          placeholder="Search employees, departments, documents"
          className="field pl-9"
        />
        {results.length > 0 && (
          <ul className="absolute z-20 mt-1 w-full overflow-hidden rounded-lg border border-ink-200 bg-white shadow-lg">
            {results.map((result) => (
              <li key={`${result.type}-${result.id}`}>
                <button
                  onClick={() => openResult(result)}
                  className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left hover:bg-ink-50"
                >
                  <span>
                    <span className="block text-sm text-ink-800">{result.title}</span>
                    <span className="block text-xs text-ink-500">{result.subtitle}</span>
                  </span>
                  <span className="text-[10px] uppercase tracking-wide text-ink-400">
                    {result.type}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <button
        className="relative rounded-lg p-2 hover:bg-ink-50"
        onClick={() => navigate("/notifications")}
        aria-label="Notifications"
      >
        <Bell className="h-5 w-5 text-ink-600" />
        {unread > 0 && (
          <span className="absolute right-1 top-1 grid h-4 min-w-4 place-items-center rounded-full bg-red-500 px-1 text-[10px] font-semibold text-white">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      <div className="flex items-center gap-2.5 pl-1">
        <span className="grid h-8 w-8 place-items-center rounded-full bg-brand-100 text-xs font-semibold text-brand-700">
          {initials(user?.full_name)}
        </span>
        <div className="hidden sm:block">
          <p className="text-sm font-medium leading-tight text-ink-800">
            {user?.full_name}
          </p>
          <p className="text-[11px] leading-tight capitalize text-ink-500">
            {user?.role?.name}
          </p>
        </div>
        <button
          onClick={() => signOut().then(() => navigate("/login"))}
          className="rounded-lg p-2 hover:bg-ink-50"
          aria-label="Sign out"
        >
          <LogOut className="h-4 w-4 text-ink-500" />
        </button>
      </div>
    </header>
  );
}
