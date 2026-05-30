import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './AuthContext';
import Layout from './components/Layout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import ReviewQueue from './pages/ReviewQueue';
import RecordDetail from './pages/RecordDetail';
import Upload from './pages/Upload';
import Batches from './pages/Batches';

function PrivateRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return (
    <div className="loading" style={{ height: '100vh' }}>
      <div className="spinner" /><span>Loading…</span>
    </div>
  );
  return user ? children : <Navigate to="/login" replace />;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={
        <PrivateRoute><Layout /></PrivateRoute>
      }>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard"  element={<Dashboard />} />
        <Route path="review"     element={<ReviewQueue />} />
        <Route path="review/:id" element={<RecordDetail />} />
        <Route path="upload"     element={<Upload />} />
        <Route path="batches"    element={<Batches />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}
