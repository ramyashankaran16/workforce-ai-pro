import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { AlertCircle, Loader2, Sparkles } from "lucide-react";
import { useAuth } from "../context/AuthContext";

export default function Login() {
  const { user, signIn, loading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  if (!loading && user) {
    return <Navigate to={location.state?.from || "/"} replace />;
  }

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signIn(email.trim(), password);
      navigate(location.state?.from || "/", { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className="flex items-center justify-center p-6">
        <div className="w-full max-w-sm">
          <div className="mb-8 flex items-center gap-2.5">
            <span className="grid h-9 w-9 place-items-center rounded-lg bg-brand-600">
              <Sparkles className="h-4.5 w-4.5 text-white" />
            </span>
            <div>
              <p className="font-semibold text-ink-900">WorkForce AI Pro</p>
              <p className="text-xs text-ink-500">HR Attrition Intelligence</p>
            </div>
          </div>

          <h1 className="text-xl font-semibold text-ink-900">Sign in</h1>
          <p className="mt-1 text-sm text-ink-500">
            Use the account your administrator created for you.
          </p>

          <form onSubmit={submit} className="mt-6 space-y-4">
            <div>
              <label className="label" htmlFor="email">Email</label>
              <input
                id="email"
                type="email"
                required
                autoComplete="username"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="field"
                placeholder="you@company.com"
              />
            </div>

            <div>
              <label className="label" htmlFor="password">Password</label>
              <input
                id="password"
                type="password"
                required
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="field"
                placeholder="••••••••"
              />
            </div>

            {error && (
              <div className="flex items-start gap-2 rounded-lg bg-red-50 px-3 py-2.5 text-sm text-red-700">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <button type="submit" className="btn-primary w-full" disabled={busy}>
              {busy && <Loader2 className="h-4 w-4 animate-spin" />}
              {busy ? "Signing in" : "Sign in"}
            </button>
          </form>

          <p className="mt-6 text-xs text-ink-400">
            Five failed attempts locks the account for 15 minutes.
          </p>
        </div>
      </div>

      <div className="hidden bg-ink-900 p-12 lg:flex lg:flex-col lg:justify-center">
        <blockquote className="max-w-md">
          <p className="text-2xl font-semibold leading-snug text-white">
            Know who is likely to leave while there is still time to do
            something about it.
          </p>
          <p className="mt-6 text-sm leading-relaxed text-ink-400">
            Attrition risk is scored from tenure, compensation position,
            engagement, workload and attendance — with the contributing factors
            shown for every individual, not just a number.
          </p>
        </blockquote>
      </div>
    </div>
  );
}
