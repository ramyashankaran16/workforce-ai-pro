import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { Spinner } from "./ui/States";

export default function ProtectedRoute({ children, permission, permissionAny }) {
  const { user, loading, can, canAny } = useAuth();
  const location = useLocation();

  if (loading) return <Spinner label="Checking your session" />;

  if (!user) {
    // remember where they were headed so login can return them there
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  const allowed =
    (!permission || can(permission)) &&
    (!permissionAny || canAny(...permissionAny));

  if (!allowed) return <Navigate to="/forbidden" replace />;

  return children;
}
