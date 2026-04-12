/**
 * Hook d'authentification avec stockage JWT dans localStorage.
 */
import { useState, useCallback, useEffect } from "react";

const API_BASE = import.meta.env.VITE_API_URL ?? "";
const TOKEN_KEY = "iris_access_token";
const REFRESH_KEY = "iris_refresh_token";

export interface AuthUser {
  id: string;
  email: string;
  name: string;
  role: string;
}

interface AuthState {
  user: AuthUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name: string) => Promise<void>;
  logout: () => void;
  getToken: () => string | null;
}

export function useAuth(): AuthState {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  const getToken = useCallback((): string | null => {
    return localStorage.getItem(TOKEN_KEY);
  }, []);

  const saveTokens = useCallback(
    (accessToken: string, refreshToken: string) => {
      localStorage.setItem(TOKEN_KEY, accessToken);
      localStorage.setItem(REFRESH_KEY, refreshToken);
    },
    []
  );

  const clearTokens = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
  }, []);

  const fetchUser = useCallback(async () => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) {
      setLoading(false);
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data: AuthUser = await res.json();
        setUser(data);
      } else {
        // Try refresh
        const refreshToken = localStorage.getItem(REFRESH_KEY);
        if (refreshToken) {
          const refreshRes = await fetch(`${API_BASE}/auth/refresh`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ refresh_token: refreshToken }),
          });
          if (refreshRes.ok) {
            const tokens = await refreshRes.json();
            saveTokens(tokens.access_token, tokens.refresh_token);
            const retryRes = await fetch(`${API_BASE}/auth/me`, {
              headers: { Authorization: `Bearer ${tokens.access_token}` },
            });
            if (retryRes.ok) {
              setUser(await retryRes.json());
            } else {
              clearTokens();
            }
          } else {
            clearTokens();
          }
        } else {
          clearTokens();
        }
      }
    } catch {
      clearTokens();
    } finally {
      setLoading(false);
    }
  }, [saveTokens, clearTokens]);

  useEffect(() => {
    fetchUser();
  }, [fetchUser]);

  const login = useCallback(
    async (email: string, password: string) => {
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Erreur" }));
        throw new Error(err.detail ?? "Erreur de connexion");
      }
      const tokens = await res.json();
      saveTokens(tokens.access_token, tokens.refresh_token);
      await fetchUser();
    },
    [saveTokens, fetchUser]
  );

  const register = useCallback(
    async (email: string, password: string, name: string) => {
      const res = await fetch(`${API_BASE}/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, name }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Erreur" }));
        throw new Error(err.detail ?? "Erreur d'inscription");
      }
      const tokens = await res.json();
      saveTokens(tokens.access_token, tokens.refresh_token);
      await fetchUser();
    },
    [saveTokens, fetchUser]
  );

  const logout = useCallback(() => {
    clearTokens();
    setUser(null);
  }, [clearTokens]);

  return { user, loading, login, register, logout, getToken };
}
