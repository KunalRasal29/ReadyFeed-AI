export function getApiErrorMessage(error, fallback = "Something went wrong.") {
  const data = error?.response?.data;

  if (!data) {
    return fallback;
  }

  if (typeof data === "string") {
    return data;
  }

  if (Array.isArray(data)) {
    return data.join(" ");
  }

  if (data.detail) {
    return data.detail;
  }

  if (data.non_field_errors?.length) {
    return data.non_field_errors.join(" ");
  }

  const firstFieldError = Object.entries(data).find(([, value]) => value);
  if (!firstFieldError) {
    return fallback;
  }

  const [field, value] = firstFieldError;
  const message = Array.isArray(value) ? value.join(" ") : String(value);
  return `${field}: ${message}`;
}

export function asArray(value) {
  return Array.isArray(value) ? value : [];
}
