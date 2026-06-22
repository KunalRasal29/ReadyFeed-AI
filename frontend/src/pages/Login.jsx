import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { getApiErrorMessage } from "../api/errors";
import { useAuth } from "../hooks/useAuth";

export default function Login() {
  const navigate = useNavigate();
  const { isAuthenticated, isLoading, login } = useAuth();
  const [form, setForm] = useState({ username: "", password: "" });
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4 text-sm font-medium text-slate-600">
        Checking session...
      </div>
    );
  }

  if (isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  const handleChange = (event) => {
    setForm((current) => ({
      ...current,
      [event.target.name]: event.target.value,
    }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);

    try {
      await login(form);
      navigate("/", { replace: true });
    } catch (apiError) {
      setError(getApiErrorMessage(apiError, "Could not log in with those credentials."));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10">
      <div className="w-full max-w-md">
        <div className="mb-7">
          <p className="text-sm font-semibold uppercase tracking-wide text-teal-700">
            READYFEED AI
          </p>
          <h1 className="mt-2 text-3xl font-semibold text-slate-950">Log in</h1>
          <p className="mt-2 text-sm text-slate-600">
            Continue curating content for offline reading, watching, and listening.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="panel space-y-5 p-6">
          {error ? (
            <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm font-medium text-red-700">
              {error}
            </div>
          ) : null}

          <label className="block">
            <span className="field-label">Username</span>
            <input
              className="field-input"
              name="username"
              value={form.username}
              onChange={handleChange}
              autoComplete="username"
              required
            />
          </label>

          <label className="block">
            <span className="field-label">Password</span>
            <input
              className="field-input"
              name="password"
              type="password"
              value={form.password}
              onChange={handleChange}
              autoComplete="current-password"
              required
            />
          </label>

          <button type="submit" className="btn-primary w-full" disabled={isSubmitting}>
            {isSubmitting ? "Logging in..." : "Log in"}
          </button>

          <p className="text-center text-sm text-slate-600">
            New here?{" "}
            <Link className="font-semibold text-teal-700 hover:text-teal-800" to="/register">
              Create an account
            </Link>
          </p>
        </form>
      </div>
    </div>
  );
}
