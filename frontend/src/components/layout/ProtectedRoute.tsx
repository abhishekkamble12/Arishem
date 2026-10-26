import React from 'react';
import { Navigate, Outlet } from 'react-router-dom';
import { useAuthStore, useActiveRole } from '../../store/authStore';

interface ProtectedRouteProps {
  allowedRoles?: Array<'admin' | 'editor' | 'viewer'>;
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ allowedRoles }: ProtectedRouteProps) => {
  const { isAuthenticated, user } = useAuthStore();
  const role = useActiveRole();

  if (!isAuthenticated) {
    // Redirect to login if user is not authenticated
    return <Navigate to="/login" replace />;
  }

  if (allowedRoles && user && !allowedRoles.includes(role)) {
    // If the user's role in this workspace is not allowed, redirect them to the home dashboard
    return <Navigate to="/" replace />;
  }

  // Render child routes
  return <Outlet />;
};
