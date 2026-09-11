import client from "./client";

const unwrap = (promise) => promise.then((response) => response.data);

export const authApi = {
  login: (email, password) => unwrap(client.post("/auth/login", { email, password })),
  me: () => unwrap(client.get("/auth/me")),
  logout: (refresh_token) => unwrap(client.post("/auth/logout", { refresh_token })),
  changePassword: (current_password, new_password) =>
    unwrap(client.post("/auth/change-password", { current_password, new_password })),
};

export const dashboardApi = {
  summary: () => unwrap(client.get("/dashboard")),
  headcount: () => unwrap(client.get("/dashboard/headcount")),
  live: () => unwrap(client.get("/monitoring/live")),
  presence: () => unwrap(client.get("/monitoring/presence")),
};

export const employeeApi = {
  list: (params) => unwrap(client.get("/employees", { params })),
  get: (id) => unwrap(client.get(`/employees/${id}`)),
  me: () => unwrap(client.get("/employees/me")),
  team: (id) => unwrap(client.get(`/employees/${id}/team`)),
  history: (id) => unwrap(client.get(`/employees/${id}/history`)),
  create: (body) => unwrap(client.post("/employees", body)),
  update: (id, body) => unwrap(client.patch(`/employees/${id}`, body)),
};

export const departmentApi = {
  list: (params) => unwrap(client.get("/departments", { params })),
  tree: () => unwrap(client.get("/departments/tree")),
};

export const attendanceApi = {
  checkIn: (body = {}) => unwrap(client.post("/attendance/check-in", body)),
  checkOut: (body = {}) => unwrap(client.post("/attendance/check-out", body)),
  mine: (params) => unwrap(client.get("/attendance/me", { params })),
  list: (params) => unwrap(client.get("/attendance", { params })),
};

export const leaveApi = {
  types: () => unwrap(client.get("/leaves/types")),
  balance: (params) => unwrap(client.get("/leaves/balance", { params })),
  mine: (params) => unwrap(client.get("/leaves/me", { params })),
  pending: (params) => unwrap(client.get("/leaves/pending", { params })),
  apply: (body) => unwrap(client.post("/leaves", body)),
  approve: (id, remarks) => unwrap(client.post(`/leaves/${id}/approve`, { remarks })),
  reject: (id, remarks) => unwrap(client.post(`/leaves/${id}/reject`, { remarks })),
  cancel: (id) => unwrap(client.post(`/leaves/${id}/cancel`)),
};

export const analyticsApi = {
  overview: (months = 12) =>
    unwrap(client.get("/analytics/attrition/overview", { params: { months } })),
  byDepartment: () => unwrap(client.get("/analytics/attrition/by-department")),
  byTenure: () => unwrap(client.get("/analytics/attrition/by-tenure")),
  exitReasons: () => unwrap(client.get("/analytics/attrition/exit-reasons")),
  drivers: () => unwrap(client.get("/analytics/attrition/drivers")),
  riskDistribution: () => unwrap(client.get("/analytics/attrition/risk-distribution")),
};

export const riskApi = {
  scores: (params) => unwrap(client.get("/risk/scores", { params })),
  employee: (id) => unwrap(client.get(`/risk/employee/${id}`)),
  heatmap: () => unwrap(client.get("/risk/heatmap")),
  evaluate: (employeeId) =>
    unwrap(
      client.post("/risk/evaluate", null, {
        params: employeeId ? { employee_id: employeeId } : {},
      })
    ),
  alerts: (params) => unwrap(client.get("/risk/alerts", { params })),
  acknowledge: (id) => unwrap(client.post(`/risk/alerts/${id}/acknowledge`)),
  resolve: (id, notes) => unwrap(client.post(`/risk/alerts/${id}/resolve`, { notes })),
};

export const predictionApi = {
  models: (params) => unwrap(client.get("/predictions/models", { params })),
  activeModel: () => unwrap(client.get("/predictions/models/active")),
  deploy: (id) => unwrap(client.post(`/predictions/models/${id}/deploy`)),
  predict: (employeeId) =>
    unwrap(client.post(`/predictions/employee/${employeeId}?explain=true`)),
  batch: () => unwrap(client.post("/predictions/batch")),
  list: (params) => unwrap(client.get("/predictions", { params })),
};

export const notificationApi = {
  list: (params) => unwrap(client.get("/notifications", { params })),
  count: () => unwrap(client.get("/notifications/count")),
  markAllRead: () => unwrap(client.post("/notifications/read-all")),
};

export const searchApi = {
  global: (q) => unwrap(client.get("/search", { params: { q } })),
};
