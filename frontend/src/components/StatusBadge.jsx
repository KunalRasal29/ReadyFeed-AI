const styles = {
  queued: "border-slate-300 bg-slate-100 text-slate-700",
  downloading: "border-blue-200 bg-blue-50 text-blue-700",
  ready: "border-emerald-200 bg-emerald-50 text-emerald-700",
  failed: "border-red-200 bg-red-50 text-red-700",
};

export default function StatusBadge({ status }) {
  return (
    <span
      className={[
        "inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold capitalize",
        styles[status] || styles.queued,
      ].join(" ")}
    >
      {status}
    </span>
  );
}
