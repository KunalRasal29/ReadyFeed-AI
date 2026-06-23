import { useCallback, useEffect, useState } from "react";

import apiClient from "../api/client";
import { asArray, getApiErrorMessage } from "../api/errors";
import StatusBadge from "../components/StatusBadge";

function formatFileSize(bytes) {
  if (!bytes) {
    return "";
  }

  if (bytes < 1024) {
    return `${bytes} B`;
  }

  return `${(bytes / 1024).toFixed(1)} KB`;
}

export default function Downloads() {
  const [downloads, setDownloads] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [pendingItemId, setPendingItemId] = useState(null);
  const [error, setError] = useState("");

  const loadDownloads = useCallback(async ({ showLoading = false } = {}) => {
    if (showLoading) {
      setIsLoading(true);
    } else {
      setIsRefreshing(true);
    }

    setError("");
    try {
      const { data } = await apiClient.get("/downloads/");
      setDownloads(asArray(data));
    } catch (apiError) {
      setError(getApiErrorMessage(apiError, "Could not load downloads."));
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadDownloads({ showLoading: true });
  }, [loadDownloads]);

  const handlePrepare = async (item) => {
    setPendingItemId(item.id);
    setError("");
    const previousDownloads = downloads;

    setDownloads((current) =>
      current.map((download) =>
        download.id === item.id
          ? { ...download, status: "downloading", error_message: "" }
          : download,
      ),
    );

    try {
      const { data } = await apiClient.post(`/downloads/${item.id}/prepare/`);
      if (data.download) {
        const nextDownload = {
          ...data.download,
          status: data.download.status === "queued" ? "downloading" : data.download.status,
          error_message: "",
        };
        setDownloads((current) =>
          current.map((download) =>
            download.id === item.id ? { ...download, ...nextDownload } : download,
          ),
        );
      }
      window.setTimeout(() => loadDownloads(), 1500);
    } catch (apiError) {
      setDownloads(previousDownloads);
      setError(getApiErrorMessage(apiError, "Could not queue preparation."));
    } finally {
      setPendingItemId(null);
    }
  };

  if (isLoading) {
    return <p className="text-sm text-slate-600">Loading downloads...</p>;
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-2xl font-semibold text-slate-950">Downloads</h2>
          <p className="mt-1 text-sm text-slate-600">
            Prepare queued items for offline access through the Celery worker.
          </p>
        </div>
        <button
          type="button"
          onClick={() => loadDownloads()}
          className="btn-secondary"
          disabled={isRefreshing}
        >
          {isRefreshing ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {error ? (
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm font-medium text-red-700">
          {error}
        </div>
      ) : null}

      {downloads.length ? (
        <div className="panel overflow-hidden">
          <div className="grid gap-4 border-b border-slate-200 px-5 py-3 text-sm font-semibold text-slate-600 sm:grid-cols-[1fr_auto_auto]">
            <span>Item</span>
            <span className="hidden sm:block">Status</span>
            <span className="hidden sm:block">Action</span>
          </div>
          {downloads.map((item) => (
            <article
              key={item.id}
              className="grid gap-4 border-b border-slate-100 px-5 py-4 last:border-b-0 sm:grid-cols-[1fr_auto_auto] sm:items-start"
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
                {item.local_file_path ? (
                  <p className="mt-2 break-all text-xs font-medium text-emerald-700">
                    Prepared file: {item.local_file_path}
                  </p>
                ) : null}
                {item.file_size_bytes ? (
                  <p className="mt-1 text-xs text-slate-500">
                    Size: {formatFileSize(item.file_size_bytes)}
                  </p>
                ) : null}
                {item.error_message ? (
                  <p className="mt-2 text-sm font-medium text-red-700">
                    {item.error_message}
                  </p>
                ) : null}
              </div>
              <div className="sm:justify-self-end">
                <StatusBadge status={item.status} />
              </div>
              <div className="sm:justify-self-end">
                {["queued", "failed"].includes(item.status) ? (
                  <button
                    type="button"
                    className="btn-primary"
                    onClick={() => handlePrepare(item)}
                    disabled={pendingItemId === item.id}
                  >
                    {pendingItemId === item.id ? "Queueing..." : "Prepare"}
                  </button>
                ) : (
                  <span className="text-sm text-slate-500">
                    {item.status === "ready" ? "Ready" : "Worker running"}
                  </span>
                )}
              </div>
            </article>
          ))}
        </div>
      ) : (
        <div className="panel p-8 text-center">
          <h3 className="text-lg font-semibold text-slate-950">No downloads yet</h3>
          <p className="mt-2 text-sm text-slate-600">
            Create a download item from the API or Django admin, then prepare it here.
          </p>
        </div>
      )}
    </div>
  );
}
