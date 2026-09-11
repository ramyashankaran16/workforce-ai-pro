# WorkForce AI Pro — Frontend

React 18 + Vite + Tailwind CSS, talking to the FastAPI backend over Axios, with
Recharts for the dashboards.

## Running it

The backend must be up first:

```powershell
cd ..\backend
uvicorn app.main:app --reload
```

Then, in a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 and sign in with the account the seed script
created.

No `.env` is needed for local development. Vite proxies `/api` to
`http://127.0.0.1:8000`, so the browser stays on a single origin and CORS never
comes into it. Set `VITE_API_BASE_URL` only when the frontend is served
separately from the API.

## Structure

```
src/
├── api/
│   ├── client.js        axios instance, auth header, refresh queue
│   └── endpoints.js     every call, grouped by module
├── context/
│   └── AuthContext.jsx  session, permissions, sign in/out
├── components/
│   ├── Layout.jsx  Sidebar.jsx  Topbar.jsx  ProtectedRoute.jsx
│   └── ui/          Card, Badge, Table, States
├── pages/
│   ├── Login.jsx  Dashboard.jsx
│   ├── Employees.jsx  EmployeeDetail.jsx
│   ├── Attendance.jsx  Leave.jsx  Payroll.jsx
│   ├── Attrition.jsx  RiskMonitor.jsx  Models.jsx
│   └── Notifications.jsx  Errors.jsx
├── hooks/useApi.js      loading/error/data, plus polling
├── utils/format.js      currency, dates, risk colours
└── config/nav.js        navigation, filtered by permission
```

## The refresh interceptor

The dashboard fires several requests at once. When the access token expires,
all of them come back 401 together.

Refreshing once per failed request would fire several refresh calls in
parallel. Since the backend revokes refresh tokens on logout and password
change, concurrent rotation is exactly the pattern that produces intermittent
"why was I logged out" reports.

So the first 401 starts a single refresh. Every other request that fails while
it is in flight parks itself in a queue and is replayed with the new token once
it lands. If the refresh itself fails, the queue is rejected, tokens are
cleared, and `AuthContext` drops the user back to the login screen rather than
leaving them on a page that will never load.

The `/auth/refresh` and `/auth/login` calls are excluded, so a failed login
cannot trigger a refresh loop.

## Permission-driven navigation

`config/nav.js` keys off permission codes, not role names:

```js
{ to: "/attrition", label: "Attrition Analytics", permission: "analytics:read_all" }
```

Keying off roles would mean editing this file every time a permission moved.
Keying off the code means the navigation follows whatever the backend actually
grants.

**Hiding a button is not a security control.** Every one of these permissions is
enforced server-side on the route itself. The UI check exists so people are not
shown things they cannot use; anyone can still call the API directly, and the
API is where the decision is made. `ProtectedRoute` redirects to `/forbidden`
rather than pretending the page does not exist.

## Token storage

Tokens live in `localStorage`. That is readable by any script on the page, so
it trades XSS resistance for simplicity and survives a refresh.

The alternative is an httpOnly cookie, which XSS cannot read — but that needs
the backend to set and clear cookies, plus CSRF protection, since cookies are
sent automatically. Given a 60-minute access token and a same-origin dev proxy,
`localStorage` is the reasonable choice here, and it is a deliberate one rather
than a default.

## Polling, not sockets, for the dashboard

`usePolling` refreshes the live snapshot every 30 seconds and pauses while the
tab is hidden, so a backgrounded dashboard stops making requests.

Headcount does not change second to second, so polling is the right tool. The
backend's WebSocket channel is there for events that genuinely need to arrive
immediately — chat messages and critical risk alerts.

## The page worth demonstrating

`/employees/:id` → **Score attrition risk**.

It returns the probability, the risk band, and the named factors behind it —
each with this person's value against the population typical, and a bar showing
which way it pushes. That comes from the backend's occlusion explainer: every
feature is replaced with the population's typical value and the model
re-scored, so the contribution is measured rather than inferred.

The composite risk panel below it breaks the 0–100 score into its eight
weighted components. When no model is deployed it says so, and explains that
the ML weight has been redistributed rather than scored as zero.

## Bundle

```
index    64 kB   application code
vendor   65 kB   axios, icons, dates
react   165 kB   react, react-dom, router
charts  433 kB   recharts and its d3 dependencies
```

Recharts is most of the weight and only three pages use it, so it is split into
its own chunk. The login screen and employee list no longer download charting
code they never render, and the vendor chunks stay cached across deploys.

## Known gaps

- **No test suite.** The backend has 324 tests; this has none. Vitest plus
  React Testing Library would be the next step, starting with the refresh
  interceptor, since that is the piece with real logic in it.
- **No WebSocket client yet.** The backend exposes `/ws/chat` and
  `/ws/monitoring`; the UI currently polls instead.
- **Chat and Documents have no screens.** The API supports both.
- **Employee create and edit are read-only in the UI.** The endpoints exist.
