import { useEffect } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import Layout from "./components/Layout";
import ProtectedRoute from "./components/ProtectedRoute";
import { useAuth } from "./hooks/useAuth";
import Commute from "./pages/Commute";
import Dashboard from "./pages/Dashboard";
import Downloads from "./pages/Downloads";
import Login from "./pages/Login";
import Preferences from "./pages/Preferences";
import Register from "./pages/Register";
import Subscriptions from "./pages/Subscriptions";

export default function App() {
  const fetchUser = useAuth((state) => state.fetchUser);

  useEffect(() => {
    fetchUser();
  }, [fetchUser]);

  return (
    <Routes>
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/subscriptions" element={<Subscriptions />} />
        <Route path="/downloads" element={<Downloads />} />
        <Route path="/commute" element={<Commute />} />
        <Route path="/preferences" element={<Preferences />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
