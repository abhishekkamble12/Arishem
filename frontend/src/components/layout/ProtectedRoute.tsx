import React from 'react';
import { Navigate, Outlet } from 'react-router-dom';
import { useAuthStore } from '../../store/authStore';

interface ProtectedRouteProps {
  allowedRoles?: Array<'admin' | 'editor' | 'viewer'>;
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ allowedRoles }: ProtectedRouteProps) => {
  const { isAuthenticated, user } = useAuthStore();

  if (!isAuthenticated) {
    // Redirect to login if user is not authenticated
    return <Navigate to="/login" replace />;
  }

  if (allowedRoles && user && !allowedRoles.includes(user.role)) {
    // If the user's role is not allowed, redirect them to the home dashboard
    return <Navigate to="/" replace />;
  }

  // Render child routes
  return <Outlet />;
};
