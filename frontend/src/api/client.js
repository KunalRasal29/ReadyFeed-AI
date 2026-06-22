import axios from "axios";

const unsafeMethods = new Set(["post", "put", "patch", "delete"]);

function getCookie(name) {
  if (typeof document === "undefined") {
    return null;
  }

  return (
    document.cookie
      .split(";")
      .map((cookie) => cookie.trim())
      .find((cookie) => cookie.startsWith(`${name}=`))
      ?.split("=")
      .slice(1)
      .join("=") || null
  );
}

const apiClient = axios.create({
  baseURL: "/api",
  withCredentials: true,
  headers: {
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest",
  },
});

apiClient.interceptors.request.use((config) => {
  const method = config.method?.toLowerCase();

  if (method && unsafeMethods.has(method)) {
    const csrfToken = getCookie("csrftoken");
    if (csrfToken) {
      config.headers["X-CSRFToken"] = decodeURIComponent(csrfToken);
    }
  }

  return config;
});

export default apiClient;
