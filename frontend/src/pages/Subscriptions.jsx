import { useEffect, useMemo, useState } from "react";

import apiClient from "../api/client";
import { asArray, getApiErrorMessage } from "../api/errors";

export default function Subscriptions() {
  const [sources, setSources] = useState([]);
  const [subscriptions, setSubscriptions] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [pendingSourceId, setPendingSourceId] = useState(null);
  const [error, setError] = useState("");

  const subscriptionBySourceId = useMemo(() => {
    return new Map(subscriptions.map((subscription) => [subscription.source, subscription]));
  }, [subscriptions]);

  const loadData = async () => {
    setIsLoading(true);
    setError("");
    try {
      const [sourcesResponse, subscriptionsResponse] = await Promise.all([
        apiClient.get("/sources/"),
        apiClient.get("/subscriptions/"),
      ]);
      setSources(asArray(sourcesResponse.data));
      setSubscriptions(asArray(subscriptionsResponse.data));
    } catch (apiError) {
      setError(getApiErrorMessage(apiError, "Could not load subscriptions."));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleToggleSubscription = async (source) => {
    setPendingSourceId(source.id);
    setError("");
    const previousSubscriptions = subscriptions;

    try {
      const existing = subscriptionBySourceId.get(source.id);
      if (existing) {
        setSubscriptions((current) =>
          current.filter((subscription) => subscription.source !== source.id),
        );
        await apiClient.delete(`/subscriptions/${existing.id}/`);
      } else {
        const optimisticSubscription = {
          id: `pending-${source.id}`,
          source: source.id,
          source_detail: source,
          priority: 1,
          is_active: true,
        };
        setSubscriptions((current) => [...current, optimisticSubscription]);
        const { data } = await apiClient.post("/subscriptions/", {
          source: source.id,
          priority: 1,
          is_active: true,
        });
        setSubscriptions((current) =>
          current.map((subscription) =>
            subscription.id === optimisticSubscription.id ? data : subscription,
          ),
        );
      }
    } catch (apiError) {
      setSubscriptions(previousSubscriptions);
      setError(getApiErrorMessage(apiError, "Could not update that subscription."));
    } finally {
      setPendingSourceId(null);
    }
  };

  if (isLoading) {
    return <p className="text-sm text-slate-600">Loading sources...</p>;
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-2xl font-semibold text-slate-950">Subscriptions</h2>
        <p className="mt-1 text-sm text-slate-600">
          Choose the sources READYFEED AI may use later for offline recommendations.
        </p>
      </div>

      {error ? (
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm font-medium text-red-700">
          {error}
        </div>
      ) : null}

      <div className="grid gap-4 md:grid-cols-2">
        {sources.length ? sources.map((source) => {
          const subscription = subscriptionBySourceId.get(source.id);
          const isSubscribed = Boolean(subscription);
          const isPending = pendingSourceId === source.id;

          return (
            <article key={source.id} className="panel p-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h3 className="text-lg font-semibold text-slate-950">{source.name}</h3>
                  <p className="mt-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                    {source.type} · {source.policy.replace("_", " ")}
                  </p>
                </div>
                <span
                  className={[
                    "rounded-full px-2.5 py-1 text-xs font-semibold",
                    isSubscribed
                      ? "bg-emerald-50 text-emerald-700"
                      : "bg-slate-100 text-slate-600",
                  ].join(" ")}
                >
                  {isSubscribed ? "Subscribed" : "Available"}
                </span>
              </div>

              <p className="mt-4 break-all text-sm text-slate-600">{source.feed_url}</p>

              <button
                type="button"
                onClick={() => handleToggleSubscription(source)}
                className={isSubscribed ? "btn-secondary mt-5" : "btn-primary mt-5"}
                disabled={isPending}
              >
                {isPending
                  ? "Updating..."
                  : isSubscribed
                    ? "Unsubscribe"
                    : "Subscribe"}
              </button>
            </article>
          );
        }) : (
          <div className="panel p-8 text-center md:col-span-2">
            <h3 className="text-lg font-semibold text-slate-950">No sources yet</h3>
            <p className="mt-2 text-sm text-slate-600">
              Run the seed command to add starter podcasts, news, and memes.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
