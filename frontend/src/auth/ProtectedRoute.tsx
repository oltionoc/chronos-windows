import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from './AuthContext';
import type { Role } from '../api/types';

// SECURITY: path a user with must_change_password=true is still allowed to
// reach — mirrors the backend's allowlist in app/main.py's
// enforce_password_change_gate. See SECURITY_REPORT.md "bootstrap admin
// credential". This is a UX convenience only; the backend enforces the same
// restriction server-side regardless of what the frontend does.
const PASSWORD_CHANGE_REQUIRED_PATH = '/settings/profile';

export function ProtectedRoute() {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) return null;
  if (!user) return <Navigate to="/login" state={{ from: location }} replace />;
  if (user.must_change_password && location.pathname !== PASSWORD_CHANGE_REQUIRED_PATH) {
    return <Navigate to={PASSWORD_CHANGE_REQUIRED_PATH} replace />;
  }

  return <Outlet />;
}

export function RoleRoute({ allow }: { allow: Role[] }) {
  // Nested under <ProtectedRoute /> everywhere it's used (see App.tsx), which
  // already redirects to PASSWORD_CHANGE_REQUIRED_PATH before this renders —
  // no need to duplicate that check here.
  const { user, loading } = useAuth();

  if (loading) return null;
  if (!user) return <Navigate to="/login" replace />;
  if (!allow.includes(user.role)) return <Navigate to="/403" replace />;

  return <Outlet />;
}
