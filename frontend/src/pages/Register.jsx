import { useEffect, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import apiClient from "../api/client";
import { asArray, getApiErrorMessage } from "../api/errors";
import TopicSelector from "../components/TopicSelector";
import { useAuth } from "../hooks/useAuth";

export default function Register() {
  const navigate = useNavigate();
  const { isAuthenticated, isLoading, register } = useAuth();
  const [sources, setSources] = useState([]);
  const [selectedSourceIds, setSelectedSourceIds] = useState([]);
  const [topics, setTopics] = useState(["AI", "Productivity"]);
  const [form, setForm] = useState({
    username: "",
    email: "",
    password: "",
    confirmPassword: "",
    maxDailyItems: 10,
    maxStorageMb: 500,
  });
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isLoadingSources, setIsLoadingSources] = useState(true);

  useEffect(() => {
    let isMounted = true;

    apiClient
      .get("/sources/")
      .then(({ data }) => {
        if (isMounted) {
          setSources(asArray(data));
        }
      })
      .catch((apiError) => {
        if (isMounted) {
          setError(getApiErrorMessage(apiError, "Could not load starter sources."));
          setSources([]);
        }
      })
      .finally(() => {
        if (isMounted) {
          setIsLoadingSources(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, []);

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4 text-sm font-medium text-slate-600">
        Checking session...
      </div>
    );
  }

  if (isAuthenticated && !isSubmitting) {
    return <Navigate to="/" replace />;
  }

  const handleChange = (event) => {
    setForm((current) => ({
      ...current,
      [event.target.name]: event.target.value,
    }));
  };

  const toggleSource = (sourceId) => {
    setSelectedSourceIds((current) =>
      current.includes(sourceId)
        ? current.filter((id) => id !== sourceId)
        : [...current, sourceId],
    );
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError("");

    if (form.password !== form.confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setIsSubmitting(true);

    try {
      await register({
        username: form.username,
        email: form.email,
        password: form.password,
      });

      await apiClient.patch("/preferences/me/", {
        topics,
        max_daily_items: Number(form.maxDailyItems),
        max_storage_mb: Number(form.maxStorageMb),
      });

      await Promise.all(
        selectedSourceIds.map((sourceId) =>
          apiClient.post("/subscriptions/", {
            source: sourceId,
            priority: 1,
            is_active: true,
          }),
        ),
      );

      navigate("/", { replace: true });
    } catch (apiError) {
      setError(getApiErrorMessage(apiError, "Could not create the account."));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 px-4 py-8 sm:px-6 lg:px-8">
      <div className="mx-auto w-full max-w-4xl">
        <div className="mb-7">
          <p className="text-sm font-semibold uppercase tracking-wide text-teal-700">
            READYFEED AI
          </p>
          <h1 className="mt-2 text-3xl font-semibold text-slate-950">
            Create your offline feed
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-slate-600">
            Choose a few starter preferences now. You can change everything later.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="panel space-y-7 p-6">
          {error ? (
            <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm font-medium text-red-700">
              {error}
            </div>
          ) : null}

          <div className="grid gap-4 sm:grid-cols-2">
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
              <span className="field-label">Email</span>
              <input
                className="field-input"
                name="email"
                type="email"
                value={form.email}
                onChange={handleChange}
                autoComplete="email"
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
                autoComplete="new-password"
                minLength={8}
                required
              />
            </label>

            <label className="block">
              <span className="field-label">Confirm password</span>
              <input
                className="field-input"
                name="confirmPassword"
                type="password"
                value={form.confirmPassword}
                onChange={handleChange}
                autoComplete="new-password"
                minLength={8}
                required
              />
            </label>
          </div>

          <section>
            <h2 className="text-base font-semibold text-slate-950">Topics</h2>
            <div className="mt-3">
              <TopicSelector value={topics} onChange={setTopics} />
            </div>
          </section>

          <section className="grid gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="field-label">Max daily items</span>
              <input
                className="field-input"
                name="maxDailyItems"
                type="number"
                min="1"
                value={form.maxDailyItems}
                onChange={handleChange}
                required
              />
            </label>

            <label className="block">
              <span className="field-label">Max storage MB</span>
              <input
                className="field-input"
                name="maxStorageMb"
                type="number"
                min="1"
                value={form.maxStorageMb}
                onChange={handleChange}
                required
              />
            </label>
          </section>

          <section>
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-base font-semibold text-slate-950">
                Starter subscriptions
              </h2>
              <p className="text-sm text-slate-500">Optional</p>
            </div>

            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              {isLoadingSources ? (
                <p className="text-sm text-slate-500">Loading sources...</p>
              ) : sources.length ? (
                sources.map((source) => {
                  const isSelected = selectedSourceIds.includes(source.id);
                  return (
                    <button
                      key={source.id}
                      type="button"
                      onClick={() => toggleSource(source.id)}
                      className={[
                        "rounded-lg border p-4 text-left transition",
                        isSelected
                          ? "border-teal-700 bg-teal-50"
                          : "border-slate-200 bg-white hover:border-slate-300",
                      ].join(" ")}
                    >
                      <span className="block text-sm font-semibold text-slate-950">
                        {source.name}
                      </span>
                      <span className="mt-1 block text-xs uppercase tracking-wide text-slate-500">
                        {source.type} · {source.policy.replace("_", " ")}
                      </span>
                    </button>
                  );
                })
              ) : (
                <p className="text-sm text-slate-500">No sources available yet.</p>
              )}
            </div>
          </section>

          <div className="flex flex-col gap-3 border-t border-slate-200 pt-5 sm:flex-row sm:items-center sm:justify-between">
            <Link className="text-sm font-semibold text-teal-700 hover:text-teal-800" to="/login">
              Already have an account?
            </Link>
            <button type="submit" className="btn-primary" disabled={isSubmitting}>
              {isSubmitting ? "Creating account..." : "Create account"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
