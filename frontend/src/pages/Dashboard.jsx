import { useEffect, useState } from "react";

import apiClient from "../api/client";
import { getApiErrorMessage } from "../api/errors";
import { useAuth } from "../hooks/useAuth";

export default function Dashboard() {
  const storeUser = useAuth((state) => state.user);
  const [profile, setProfile] = useState(storeUser);
  const [preferences, setPreferences] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const user = profile || storeUser;

  useEffect(() => {
    let isMounted = true;

    async function loadDashboard() {
      setIsLoading(true);
      setError("");
      const [profileResponse, preferenceResponse] = await Promise.all([
        apiClient.get("/auth/me/"),
        apiClient.get("/preferences/me/"),
      ]);

      if (isMounted) {
        setProfile(profileResponse.data);
        setPreferences(preferenceResponse.data);
        setIsLoading(false);
      }
    }

    loadDashboard().catch((apiError) => {
      if (isMounted) {
        setError(getApiErrorMessage(apiError, "Could not load dashboard."));
        setIsLoading(false);
      }
    });

    return () => {
      isMounted = false;
    };
  }, []);

  if (isLoading) {
    return <p className="text-sm text-slate-600">Loading dashboard...</p>;
  }

  return (
    <div className="space-y-6">
      <section>
        <h2 className="text-2xl font-semibold text-slate-950">
          Welcome, {user?.username}
        </h2>
        <p className="mt-1 text-sm text-slate-600">
          Your offline content profile is ready for the next build phase.
        </p>
      </section>

      {error ? (
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm font-medium text-red-700">
          {error}
        </div>
      ) : null}

      <section className="grid gap-4 md:grid-cols-3">
        <div className="panel p-5">
          <p className="text-sm font-medium text-slate-500">Username</p>
          <p className="mt-2 text-xl font-semibold text-slate-950">{user?.username}</p>
        </div>
        <div className="panel p-5">
          <p className="text-sm font-medium text-slate-500">Email</p>
          <p className="mt-2 break-words text-xl font-semibold text-slate-950">
            {user?.email || "Not set"}
          </p>
        </div>
        <div className="panel p-5">
          <p className="text-sm font-medium text-slate-500">User ID</p>
          <p className="mt-2 text-xl font-semibold text-slate-950">{user?.id}</p>
        </div>
      </section>

      <section className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
        <div className="panel p-5">
          <div className="flex items-center justify-between gap-4">
            <h3 className="text-lg font-semibold text-slate-950">Selected topics</h3>
            <p className="text-sm text-slate-500">
              {preferences?.max_daily_items || 0} items/day
            </p>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {preferences?.topics?.length ? (
              preferences.topics.map((topic) => (
                <span
                  key={topic}
                  className="rounded-full border border-teal-200 bg-teal-50 px-3 py-1 text-sm font-medium text-teal-800"
                >
                  {topic}
                </span>
              ))
            ) : (
              <p className="text-sm text-slate-500">No topics selected yet.</p>
            )}
          </div>
          <p className="mt-5 text-sm text-slate-600">
            Storage limit: {preferences?.max_storage_mb || 0} MB
          </p>
        </div>

        <div className="panel border-dashed p-5">
          <h3 className="text-lg font-semibold text-slate-950">Coming next</h3>
          <p className="mt-3 text-sm text-slate-600">
            AI content discovery will be added later
          </p>
        </div>
      </section>
    </div>
  );
}
