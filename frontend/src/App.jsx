import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import Layout from "./components/Layout";
import ProtectedRoute from "./components/ProtectedRoute";

import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Employees from "./pages/Employees";
import EmployeeDetail from "./pages/EmployeeDetail";
import Attendance from "./pages/Attendance";
import Leave from "./pages/Leave";
import Payroll from "./pages/Payroll";
import Attrition from "./pages/Attrition";
import RiskMonitor from "./pages/RiskMonitor";
import Models from "./pages/Models";
import Notifications from "./pages/Notifications";
import { Forbidden, NotFound } from "./pages/Errors";

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/forbidden" element={<Forbidden />} />

          <Route
            element={
              <ProtectedRoute>
                <Layout />
              </ProtectedRoute>
            }
          >
            <Route index element={<Dashboard />} />
            <Route path="notifications" element={<Notifications />} />
            <Route path="attendance" element={<Attendance />} />
            <Route path="leave" element={<Leave />} />
            <Route path="payroll" element={<Payroll />} />

            <Route
              path="employees"
              element={
                <ProtectedRoute permission="employee:read">
                  <Employees />
                </ProtectedRoute>
              }
            />
            <Route
              path="employees/:id"
              element={
                <ProtectedRoute permission="employee:read">
                  <EmployeeDetail />
                </ProtectedRoute>
              }
            />
            <Route
              path="attrition"
              element={
                <ProtectedRoute permission="analytics:read_all">
                  <Attrition />
                </ProtectedRoute>
              }
            />
            <Route
              path="risk"
              element={
                <ProtectedRoute permissionAny={["risk:read_team", "risk:read_all"]}>
                  <RiskMonitor />
                </ProtectedRoute>
              }
            />
            <Route
              path="models"
              element={
                <ProtectedRoute permission="prediction:read">
                  <Models />
                </ProtectedRoute>
              }
            />
          </Route>

          <Route path="*" element={<NotFound />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
