const topicOptions = [
  "AI",
  "Python",
  "Productivity",
  "Science",
  "Startups",
  "Design",
  "News",
  "Health",
  "Finance",
  "Learning",
];

export default function TopicSelector({ value, onChange }) {
  const selected = new Set(value);

  const toggleTopic = (topic) => {
    if (selected.has(topic)) {
      onChange(value.filter((item) => item !== topic));
    } else {
      onChange([...value, topic]);
    }
  };

  return (
    <div className="flex flex-wrap gap-2">
      {topicOptions.map((topic) => {
        const isSelected = selected.has(topic);
        return (
          <button
            key={topic}
            type="button"
            onClick={() => toggleTopic(topic)}
            className={[
              "chip",
              isSelected
                ? "border-teal-700 bg-teal-700 text-white"
                : "border-slate-300 bg-white text-slate-700 hover:border-teal-600 hover:text-teal-700",
            ].join(" ")}
          >
            {topic}
          </button>
        );
      })}
    </div>
  );
}
