import {
  BarChart3, CalendarCheck, FileText, Gauge, LayoutDashboard,
  ShieldAlert, Users, Wallet,
} from "lucide-react";

/*
 * Navigation is filtered by permission, not by role name.
 *
 * Keying off roles would mean editing this file every time a permission moves;
 * keying off the permission code means the nav follows whatever the backend
 * actually grants.
 */
export const NAV_ITEMS = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, permission: null },
  { to: "/employees", label: "Employees", icon: Users, permission: "employee:read" },
  { to: "/attendance", label: "Attendance", icon: CalendarCheck, permission: null },
  { to: "/leave", label: "Leave", icon: FileText, permission: null },
  { to: "/payroll", label: "Payroll", icon: Wallet, permission: "payroll:read_own" },
  {
    to: "/attrition",
    label: "Attrition Analytics",
    icon: BarChart3,
    permission: "analytics:read_all",
  },
  {
    to: "/risk",
    label: "Risk Monitor",
    icon: ShieldAlert,
    permissionAny: ["risk:read_team", "risk:read_all"],
  },
  { to: "/models", label: "AI Models", icon: Gauge, permission: "prediction:read" },
];
