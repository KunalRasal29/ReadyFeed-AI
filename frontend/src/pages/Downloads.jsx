import { useEffect, useState } from "react";

import apiClient from "../api/client";
import { asArray, getApiErrorMessage } from "../api/errors";
import StatusBadge from "../components/StatusBadge";

export default function Downloads() {
  const [downloads, setDownloads] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let isMounted = true;

    apiClient
      .get("/downloads/")
      .then(({ data }) => {
        if (isMounted) {
          setDownloads(asArray(data));
        }
      })
      .catch((apiError) => {
        if (isMounted) {
          setError(getApiErrorMessage(apiError, "Could not load downloads."));
        }
      })
      .finally(() => {
        if (isMounted) {
          setIsLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, []);

  if (isLoading) {
    return <p className="text-sm text-slate-600">Loading downloads...</p>;
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-2xl font-semibold text-slate-950">Downloads</h2>
        <p className="mt-1 text-sm text-slate-600">
          The queue is ready for future download workers.
        </p>
      </div>

      {error ? (
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm font-medium text-red-700">
          {error}
        </div>
      ) : null}

      {downloads.length ? (
        <div className="panel overflow-hidden">
          <div className="grid grid-cols-[1fr_auto] gap-4 border-b border-slate-200 px-5 py-3 text-sm font-semibold text-slate-600">
            <span>Item</span>
            <span>Status</span>
          </div>
          {downloads.map((item) => (
            <article
              key={item.id}
              className="grid grid-cols-[1fr_auto] gap-4 border-b border-slate-100 px-5 py-4 last:border-b-0"
            >
              <div>
                <h3 className="font-semibold text-slate-950">{item.title}</h3>
                <p className="mt-1 text-sm text-slate-600">
                  {item.source_detail?.name || "Unknown source"}
                </p>
                {item.description ? (
                  <p className="mt-2 line-clamp-2 text-sm text-slate-500">
                    {item.description}
                  </p>
                ) : null}
              </div>
              <StatusBadge status={item.status} />
            </article>
          ))}
        </div>
      ) : (
        <div className="panel p-8 text-center">
          <h3 className="text-lg font-semibold text-slate-950">No downloads yet</h3>
          <p className="mt-2 text-sm text-slate-600">
            Download scheduling will appear here after the backend worker phase.
          </p>
        </div>
      )}
    </div>
  );
}
