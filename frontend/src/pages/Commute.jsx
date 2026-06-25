import { useCallback, useEffect, useMemo, useState } from "react";

import apiClient from "../api/client";
import { asArray, getApiErrorMessage } from "../api/errors";

const weekdays = [
  { value: "mon", short: "Mon", label: "Monday" },
  { value: "tue", short: "Tue", label: "Tuesday" },
  { value: "wed", short: "Wed", label: "Wednesday" },
  { value: "thu", short: "Thu", label: "Thursday" },
  { value: "fri", short: "Fri", label: "Friday" },
  { value: "sat", short: "Sat", label: "Saturday" },
  { value: "sun", short: "Sun", label: "Sunday" },
];

const emptyForm = {
  id: null,
  label: "",
  start_time: "09:00",
  end_time: "10:00",
  days_of_week: ["mon", "tue", "wed", "thu", "fri"],
  is_active: true,
};

function toTimeInputValue(value) {
  return (value || "").slice(0, 5);
}

function toApiTimeValue(value) {
  if (!value) {
    return "";
  }

  return value.length === 5 ? `${value}:00` : value;
}

function normalizedDays(days) {
  const selected = new Set(asArray(days).map((day) => String(day).toLowerCase()));
  return weekdays.filter((day) => selected.has(day.value)).map((day) => day.value);
}

function formatDays(days) {
  const selectedDays = normalizedDays(days);
  if (!selectedDays.length) {
    return "No days selected";
  }

  return selectedDays
    .map((day) => weekdays.find((weekday) => weekday.value === day)?.short || day)
    .join(", ");
}

function formatTimeRange(commute) {
  return `${toTimeInputValue(commute.start_time)} - ${toTimeInputValue(commute.end_time)}`;
}

export default function Commute() {
  const [commutes, setCommutes] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [pendingWindowId, setPendingWindowId] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const editingCommute = useMemo(
    () => commutes.find((commute) => commute.id === form.id),
    [commutes, form.id],
  );

  const loadCommutes = useCallback(async ({ showLoading = false } = {}) => {
    if (showLoading) {
      setIsLoading(true);
    }

    setError("");
    try {
      const { data } = await apiClient.get("/commute/");
      setCommutes(asArray(data));
    } catch (apiError) {
      setError(getApiErrorMessage(apiError, "Could not load commute windows."));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadCommutes({ showLoading: true });
  }, [loadCommutes]);

  const updateForm = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  const toggleDay = (day) => {
    setForm((current) => {
      const selectedDays = new Set(normalizedDays(current.days_of_week));
      if (selectedDays.has(day)) {
        selectedDays.delete(day);
      } else {
        selectedDays.add(day);
      }

      return {
        ...current,
        days_of_week: weekdays
          .filter((weekday) => selectedDays.has(weekday.value))
          .map((weekday) => weekday.value),
      };
    });
  };

  const resetForm = () => {
    setForm(emptyForm);
    setError("");
    setNotice("");
  };

  const editCommute = (commute) => {
    setForm({
      id: commute.id,
      label: commute.label || "",
      start_time: toTimeInputValue(commute.start_time),
      end_time: toTimeInputValue(commute.end_time),
      days_of_week: normalizedDays(commute.days_of_week),
      is_active: Boolean(commute.is_active),
    });
    setError("");
    setNotice("");
  };

  const saveCommute = async (event) => {
    event.preventDefault();
    setIsSaving(true);
    setError("");
    setNotice("");

    const payload = {
      label: form.label.trim(),
      start_time: toApiTimeValue(form.start_time),
      end_time: toApiTimeValue(form.end_time),
      days_of_week: normalizedDays(form.days_of_week),
      is_active: form.is_active,
    };

    try {
      const request = form.id
        ? apiClient.patch(`/commute/${form.id}/`, payload)
        : apiClient.post("/commute/", payload);
      const { data } = await request;

      setCommutes((current) => {
        if (form.id) {
          return current.map((commute) => (commute.id === data.id ? data : commute));
        }

        return [...current, data].sort((first, second) =>
          `${first.start_time}${first.label}`.localeCompare(
            `${second.start_time}${second.label}`,
          ),
        );
      });
      setForm(emptyForm);
      setNotice(form.id ? "Commute window updated." : "Commute window added.");
    } catch (apiError) {
      setError(getApiErrorMessage(apiError, "Could not save commute window."));
    } finally {
      setIsSaving(false);
    }
  };

  const toggleActive = async (commute) => {
    setPendingWindowId(commute.id);
    setError("");
    setNotice("");

    try {
      const { data } = await apiClient.patch(`/commute/${commute.id}/`, {
        is_active: !commute.is_active,
      });
      setCommutes((current) =>
        current.map((window) => (window.id === data.id ? data : window)),
      );
      setNotice(data.is_active ? "Commute window activated." : "Commute window paused.");
    } catch (apiError) {
      setError(getApiErrorMessage(apiError, "Could not update commute window."));
    } finally {
      setPendingWindowId(null);
    }
  };

  const deleteCommute = async (commute) => {
    setPendingWindowId(commute.id);
    setError("");
    setNotice("");
    const previousCommutes = commutes;

    setCommutes((current) => current.filter((window) => window.id !== commute.id));
    if (form.id === commute.id) {
      setForm(emptyForm);
    }

    try {
      await apiClient.delete(`/commute/${commute.id}/`);
      setNotice("Commute window deleted.");
    } catch (apiError) {
      setCommutes(previousCommutes);
      setError(getApiErrorMessage(apiError, "Could not delete commute window."));
    } finally {
      setPendingWindowId(null);
    }
  };

  if (isLoading) {
    return <p className="text-sm text-slate-600">Loading commute schedule...</p>;
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-2xl font-semibold text-slate-950">Commute Schedule</h2>
        <p className="mt-1 text-sm text-slate-600">
          READYFEED prepares queued downloads four hours before active windows.
        </p>
      </div>

      {error ? (
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm font-medium text-red-700">
          {error}
        </div>
      ) : null}

      {notice ? (
        <div className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm font-medium text-emerald-700">
          {notice}
        </div>
      ) : null}

      <div className="grid gap-5 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <form onSubmit={saveCommute} className="panel space-y-5 p-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="text-lg font-semibold text-slate-950">
                {editingCommute ? "Edit Window" : "New Window"}
              </h3>
              <p className="mt-1 text-sm text-slate-500">
                {editingCommute ? editingCommute.label : "Create a recurring commute"}
              </p>
            </div>
            {editingCommute ? (
              <button type="button" className="btn-secondary" onClick={resetForm}>
                New
              </button>
            ) : null}
          </div>

          <label className="block">
            <span className="field-label">Label</span>
            <input
              className="field-input"
              type="text"
              value={form.label}
              onChange={(event) => updateForm("label", event.target.value)}
              placeholder="Morning commute"
              required
            />
          </label>

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="field-label">Start time</span>
              <input
                className="field-input"
                type="time"
                value={form.start_time}
                onChange={(event) => updateForm("start_time", event.target.value)}
                required
              />
            </label>

            <label className="block">
              <span className="field-label">End time</span>
              <input
                className="field-input"
                type="time"
                value={form.end_time}
                onChange={(event) => updateForm("end_time", event.target.value)}
                required
              />
            </label>
          </div>

          <fieldset>
            <legend className="field-label">Days</legend>
            <div className="mt-2 flex flex-wrap gap-2">
              {weekdays.map((day) => {
                const isSelected = normalizedDays(form.days_of_week).includes(day.value);
                return (
                  <button
                    key={day.value}
                    type="button"
                    onClick={() => toggleDay(day.value)}
                    aria-pressed={isSelected}
                    className={[
                      "chip",
                      isSelected
                        ? "border-teal-700 bg-teal-700 text-white"
                        : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50",
                    ].join(" ")}
                  >
                    {day.short}
                  </button>
                );
              })}
            </div>
          </fieldset>

          <label className="flex items-center gap-3 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-medium text-slate-700">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(event) => updateForm("is_active", event.target.checked)}
              className="h-4 w-4 rounded border-slate-300 text-teal-700 focus:ring-teal-600"
            />
            Active
          </label>

          <div className="border-t border-slate-200 pt-5">
            <button type="submit" className="btn-primary" disabled={isSaving}>
              {isSaving ? "Saving..." : editingCommute ? "Save changes" : "Add window"}
            </button>
          </div>
        </form>

        <section className="space-y-3">
          {commutes.length ? (
            commutes.map((commute) => (
              <article key={commute.id} className="panel p-5">
                <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="text-lg font-semibold text-slate-950">
                        {commute.label}
                      </h3>
                      <span
                        className={[
                          "rounded-full px-2.5 py-1 text-xs font-semibold",
                          commute.is_active
                            ? "bg-emerald-50 text-emerald-700"
                            : "bg-slate-100 text-slate-600",
                        ].join(" ")}
                      >
                        {commute.is_active ? "Active" : "Paused"}
                      </span>
                    </div>
                    <p className="mt-2 text-sm font-medium text-slate-700">
                      {formatTimeRange(commute)}
                    </p>
                    <p className="mt-1 text-sm text-slate-500">
                      {formatDays(commute.days_of_week)}
                    </p>
                  </div>

                  <div className="flex flex-wrap gap-2 sm:justify-end">
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={() => editCommute(commute)}
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={() => toggleActive(commute)}
                      disabled={pendingWindowId === commute.id}
                    >
                      {pendingWindowId === commute.id
                        ? "Updating..."
                        : commute.is_active
                          ? "Pause"
                          : "Activate"}
                    </button>
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={() => deleteCommute(commute)}
                      disabled={pendingWindowId === commute.id}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              </article>
            ))
          ) : (
            <div className="panel p-8 text-center">
              <h3 className="text-lg font-semibold text-slate-950">
                No commute windows yet
              </h3>
              <p className="mt-2 text-sm text-slate-600">
                Add a recurring window to let the scheduler prepare queued items.
              </p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
