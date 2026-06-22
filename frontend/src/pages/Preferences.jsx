import { useEffect, useState } from "react";

import apiClient from "../api/client";
import { asArray, getApiErrorMessage } from "../api/errors";
import TopicSelector from "../components/TopicSelector";

export default function Preferences() {
  const [preferenceId, setPreferenceId] = useState(null);
  const [topics, setTopics] = useState([]);
  const [maxDailyItems, setMaxDailyItems] = useState(10);
  const [maxStorageMb, setMaxStorageMb] = useState(500);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    let isMounted = true;

    async function loadPreferences() {
      setIsLoading(true);
      setError("");
      const { data } = await apiClient.get("/preferences/");
      const preference = asArray(data)[0] || (await apiClient.get("/preferences/me/")).data;

      if (isMounted) {
        setPreferenceId(preference.id);
        setTopics(asArray(preference.topics));
        setMaxDailyItems(preference.max_daily_items ?? 10);
        setMaxStorageMb(preference.max_storage_mb ?? 500);
        setIsLoading(false);
      }
    }

    loadPreferences().catch((apiError) => {
      if (isMounted) {
        setError(getApiErrorMessage(apiError, "Could not load preferences."));
        setIsLoading(false);
      }
    });

    return () => {
      isMounted = false;
    };
  }, []);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setIsSaving(true);
    setError("");
    setSuccess("");

    try {
      const payload = {
        topics,
        max_daily_items: Number(maxDailyItems),
        max_storage_mb: Number(maxStorageMb),
      };
      const url = preferenceId ? `/preferences/${preferenceId}/` : "/preferences/me/";
      const { data } = await apiClient.patch(url, payload);
      setPreferenceId(data.id);
      setTopics(asArray(data.topics));
      setMaxDailyItems(data.max_daily_items ?? 10);
      setMaxStorageMb(data.max_storage_mb ?? 500);
      setSuccess("Preferences saved.");
    } catch (apiError) {
      setError(getApiErrorMessage(apiError, "Could not save preferences."));
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return <p className="text-sm text-slate-600">Loading preferences...</p>;
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-2xl font-semibold text-slate-950">Preferences</h2>
        <p className="mt-1 text-sm text-slate-600">
          Tune what READYFEED AI should prioritize once discovery is added.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="panel space-y-6 p-6">
        {error ? (
          <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm font-medium text-red-700">
            {error}
          </div>
        ) : null}

        {success ? (
          <div className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm font-medium text-emerald-700">
            {success}
          </div>
        ) : null}

        <section>
          <h3 className="text-base font-semibold text-slate-950">Topics</h3>
          <div className="mt-3">
            <TopicSelector value={topics} onChange={setTopics} />
          </div>
        </section>

        <section className="grid gap-4 sm:grid-cols-2">
          <label className="block">
            <span className="field-label">Max daily items</span>
            <input
              className="field-input"
              type="number"
              min="1"
              value={maxDailyItems}
              onChange={(event) => setMaxDailyItems(event.target.value)}
              required
            />
          </label>

          <label className="block">
            <span className="field-label">Max storage MB</span>
            <input
              className="field-input"
              type="number"
              min="1"
              value={maxStorageMb}
              onChange={(event) => setMaxStorageMb(event.target.value)}
              required
            />
          </label>
        </section>

        <div className="border-t border-slate-200 pt-5">
          <button type="submit" className="btn-primary" disabled={isSaving}>
            {isSaving ? "Saving..." : "Save preferences"}
          </button>
        </div>
      </form>
    </div>
  );
}
