import { useAuthStore } from "../stores/authStore";

export function useAuth(selector) {
  return useAuthStore(selector);
}
