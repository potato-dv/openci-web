import { useEffect, useState } from "react";

import { getProfile, login as loginRequest } from "../services/api";
import type { User } from "../types/api";

const ACCESS_TOKEN_KEY = "access_token";

export function useAuth() {
  const [accessToken, setAccessToken] = useState("");
  const [user, setUser] = useState<User | null>(null);
  const [isInitializing, setIsInitializing] = useState(() =>
    Boolean(sessionStorage.getItem(ACCESS_TOKEN_KEY)),
  );

  useEffect(() => {
    const storedToken = sessionStorage.getItem(ACCESS_TOKEN_KEY);

    if (!storedToken) {
      return;
    }

    const token = storedToken;
    let cancelled = false;

    async function restoreSession() {
      try {
        const profile = await getProfile(token);

        if (!cancelled) {
          setAccessToken(token);
          setUser(profile);
        }
      } catch {
        sessionStorage.removeItem(ACCESS_TOKEN_KEY);
      } finally {
        if (!cancelled) {
          setIsInitializing(false);
        }
      }
    }

    void restoreSession();

    return () => {
      cancelled = true;
    };
  }, []);

  async function login(email: string, password: string) {
    const data = await loginRequest(email, password);
    const profile = await getProfile(data.access_token);

    sessionStorage.setItem(ACCESS_TOKEN_KEY, data.access_token);
    setAccessToken(data.access_token);
    setUser(profile);
  }

  function logout() {
    sessionStorage.removeItem(ACCESS_TOKEN_KEY);
    setAccessToken("");
    setUser(null);
  }

  return {
    accessToken,
    user,
    isInitializing,
    login,
    logout,
  };
}
