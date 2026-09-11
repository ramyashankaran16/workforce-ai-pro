import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { authApi } from "../api/endpoints";
import { setAuthFailureHandler, tokens } from "../api/client";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const signOut = useCallback(async () => {
    const refresh = tokens.refresh();
    if (refresh) {
      // best effort: if the call fails the local tokens still go
      await authApi.logout(refresh).catch(() => {});
    }
    tokens.clear();
    setUser(null);
  }, []);

  // The axios layer calls this when a refresh fails, so an expired session
  // clears the UI instead of leaving a logged-out user on a broken page.
  useEffect(() => {
    setAuthFailureHandler(() => {
      tokens.clear();
      setUser(null);
    });
  }, []);

  useEffect(() => {
    if (!tokens.access()) {
      setLoading(false);
      return;
    }
    authApi
      .me()
      .then(setUser)
      .catch(() => tokens.clear())
      .finally(() => setLoading(false));
  }, []);

  const signIn = useCallback(async (email, password) => {
    const data = await authApi.login(email, password);
    tokens.set(data.access_token, data.refresh_token);
    setUser(data.user ?? (await authApi.me()));
    return data.user;
  }, []);

  const value = useMemo(() => {
    const permissions = new Set(user?.permissions ?? []);
    return {
      user,
      loading,
      signIn,
      signOut,
      role: user?.role?.name ?? null,
      /*
       * Used to hide navigation and buttons a user cannot action.
       *
       * This is presentation only. The same permission is enforced server-side
       * on every route -- hiding a button is a courtesy, not a security
       * control, and anyone can call the API directly.
       */
      can: (code) => permissions.has(code),
      canAny: (...codes) => codes.some((code) => permissions.has(code)),
    };
  }, [user, loading, signIn, signOut]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
