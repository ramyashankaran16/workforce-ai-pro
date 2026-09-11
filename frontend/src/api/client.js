import axios from "axios";

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "";

export const ACCESS_KEY = "wfp_access";
export const REFRESH_KEY = "wfp_refresh";

export const tokens = {
  access: () => localStorage.getItem(ACCESS_KEY),
  refresh: () => localStorage.getItem(REFRESH_KEY),
  set(access, refresh) {
    if (access) localStorage.setItem(ACCESS_KEY, access);
    if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};

const client = axios.create({
  baseURL: `${BASE_URL}/api/v1`,
  headers: { "Content-Type": "application/json" },
  timeout: 30000,
});

client.interceptors.request.use((config) => {
  const token = tokens.access();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

/*
 * Refresh handling.
 *
 * The problem this solves: a dashboard fires five requests at once and all
 * five come back 401 because the access token just expired. Refreshing once
 * per failed request would burn five refresh calls, and since the backend
 * revokes tokens on password change and logout, concurrent rotation is
 * exactly the kind of thing that produces intermittent logouts.
 *
 * So the first 401 starts a single refresh; every other request that fails
 * while it is in flight parks itself in `queue` and is replayed once the new
 * token lands.
 */
let refreshing = null;
let queue = [];

function flushQueue(error, token = null) {
  queue.forEach(({ resolve, reject }) => (error ? reject(error) : resolve(token)));
  queue = [];
}

let onAuthFailure = () => {};
export function setAuthFailureHandler(handler) {
  onAuthFailure = handler;
}

client.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    const status = error.response?.status;

    if (status !== 401 || !original || original._retried) {
      return Promise.reject(normalise(error));
    }

    // Never try to refresh the refresh call itself, or a failed login.
    if (
      original.url?.includes("/auth/refresh") ||
      original.url?.includes("/auth/login")
    ) {
      return Promise.reject(normalise(error));
    }

    const refreshToken = tokens.refresh();
    if (!refreshToken) {
      onAuthFailure();
      return Promise.reject(normalise(error));
    }

    original._retried = true;

    if (refreshing) {
      return new Promise((resolve, reject) => {
        queue.push({
          resolve: (token) => {
            original.headers.Authorization = `Bearer ${token}`;
            resolve(client(original));
          },
          reject,
        });
      });
    }

    refreshing = axios
      .post(`${BASE_URL}/api/v1/auth/refresh`, { refresh_token: refreshToken })
      .then(({ data }) => {
        tokens.set(data.access_token, null);
        flushQueue(null, data.access_token);
        return data.access_token;
      })
      .catch((refreshError) => {
        flushQueue(refreshError, null);
        tokens.clear();
        onAuthFailure();
        throw refreshError;
      })
      .finally(() => {
        refreshing = null;
      });

    const token = await refreshing;
    original.headers.Authorization = `Bearer ${token}`;
    return client(original);
  }
);

/** Turn the backend's error envelope into a plain Error with a usable message. */
function normalise(error) {
  const payload = error.response?.data;
  const detail = payload?.error?.message;

  let message = "Something went wrong.";
  if (typeof detail === "string") {
    message = detail;
  } else if (Array.isArray(detail)) {
    message = detail.map((d) => `${d.field}: ${d.message}`).join("; ");
  } else if (error.code === "ECONNABORTED") {
    message = "The request timed out.";
  } else if (!error.response) {
    message = "Cannot reach the server. Is the backend running?";
  }

  const wrapped = new Error(message);
  wrapped.status = error.response?.status;
  wrapped.code = payload?.error?.code;
  return wrapped;
}

export default client;
