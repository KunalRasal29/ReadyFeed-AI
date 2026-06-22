import { create } from "zustand";

import apiClient from "../api/client";

export const useAuthStore = create((set) => ({
  user: null,
  isAuthenticated: false,
  isLoading: true,

  fetchUser: async () => {
    set({ isLoading: true });
    try {
      const { data } = await apiClient.get("/auth/me/");
      set({ user: data, isAuthenticated: true, isLoading: false });
      return data;
    } catch {
      set({ user: null, isAuthenticated: false, isLoading: false });
      return null;
    }
  },

  login: async ({ username, password }) => {
    const { data } = await apiClient.post("/auth/login/", { username, password });
    set({ user: data, isAuthenticated: true, isLoading: false });
    await useAuthStore.getState().fetchUser();
    return data;
  },

  register: async ({ username, email, password }) => {
    const { data } = await apiClient.post("/auth/register/", {
      username,
      email,
      password,
    });
    set({ user: data, isAuthenticated: true, isLoading: false });
    await useAuthStore.getState().fetchUser();
    return data;
  },

  logout: async () => {
    try {
      await apiClient.post("/auth/logout/");
    } finally {
      set({ user: null, isAuthenticated: false, isLoading: false });
    }
  },
}));
