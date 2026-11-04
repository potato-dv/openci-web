import { useEffect, useRef, useState } from "react";

import { getProfile, login as loginRequest } from "@/features/auth/api";
import type { User } from "@/types/api";
import {
  accessTokenSubject,
  clearCurrentAccessToken,
  refreshAccessToken,
  requestJson,
  setCurrentAccessToken,
  subscribeToReauthenticationRequired,
  logoutRemoteSession,
} from "@/services/http";

const ACTIVITY_EVENTS: ReadonlyArray<{
  type: string;
  options?: AddEventListenerOptions;
}> = [
  { type: "click", options: { passive: true } },
  { type: "keydown" },
  { type: "scroll", options: { capture: true, passive: true } },
  { type: "touchstart", options: { passive: true } },
  { type: "pointerdown", options: { passive: true } },
  { type: "dragstart", options: { passive: true } },
];

export function useAuth() {
  const [accessToken, setAccessToken] = useState("");
  const [user, setUser] = useState<User | null>(null);
  const [reauthRequired, setReauthRequired] = useState(false);
  const [isInitializing, setIsInitializing] = useState(true);
  const lastActivitySentAt = useRef(0);

  useEffect(() => subscribeToReauthenticationRequired(() => {
    clearCurrentAccessToken();
    setReauthRequired(true);
  }), []);

  useEffect(() => {
    let cancelled = false;
    try {
      // Remove the access token written by the pre-refresh auth implementation.
      sessionStorage.removeItem("access_token");
    } catch {
      // Storage may be unavailable in privacy-restricted browser contexts.
    }

    async function restoreSession() {
      try {
        const token = await refreshAccessToken();
        const profile = await getProfile(token);
        if (cancelled) return;
        setCurrentAccessToken(token, profile.id);
        setAccessToken(token);
        setUser(profile);
        setReauthRequired(false);
        lastActivitySentAt.current = Date.now();
      } catch {
        if (!cancelled) {
          clearCurrentAccessToken();
          setUser(null);
          setReauthRequired(false);
        }
      } finally {
        if (!cancelled) setIsInitializing(false);
      }
    }

    void restoreSession();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!user || reauthRequired) return;

    const recordActivity: EventListener = () => {
      if (document.visibilityState === "hidden") return;
      const now = Date.now();
      if (now - lastActivitySentAt.current < 60_000) return;
      lastActivitySentAt.current = now;
      void requestJson<void>("/users/activity", { token: accessToken }).catch(() => {
        // Session errors trigger the reauthentication state; transient network
        // errors leave the current page and its in-progress form untouched.
      });
    };

    for (const { type, options } of ACTIVITY_EVENTS) {
      document.addEventListener(type, recordActivity, options);
    }
    return () => {
      for (const { type, options } of ACTIVITY_EVENTS) {
        document.removeEventListener(type, recordActivity, options);
      }
    };
  }, [user, reauthRequired, accessToken]);

  async function finishLogin(email: string, password: string) {
    const data = await loginRequest(email, password);
    const subject = accessTokenSubject(data.access_token);
    if (subject === null) throw new Error("The server returned an invalid sign-in session.");
    setCurrentAccessToken(data.access_token, subject);

    try {
      const profile = await getProfile(data.access_token);
      if (profile.id !== subject) throw new Error("The sign-in session did not match this account.");
      return { token: data.access_token, profile };
    } catch (error) {
      clearCurrentAccessToken();
      void logoutRemoteSession();
      throw error;
    }
  }

  async function login(email: string, password: string) {
    const { token, profile } = await finishLogin(email, password);
    setAccessToken(token);
    setUser(profile);
    setReauthRequired(false);
    setIsInitializing(false);
    lastActivitySentAt.current = Date.now();
  }

  async function reauthenticate(email: string, password: string) {
    const { token, profile } = await finishLogin(email, password);
    setCurrentAccessToken(token, profile.id);
    if (user?.id !== profile.id) setAccessToken(token);
    setUser(profile);
    setReauthRequired(false);
    lastActivitySentAt.current = Date.now();
  }

  function logout() {
    clearCurrentAccessToken();
    setAccessToken("");
    setUser(null);
    setReauthRequired(false);
    void logoutRemoteSession();
  }

  return {
    accessToken,
    user,
    isInitializing,
    reauthRequired,
    login,
    reauthenticate,
    logout,
  };
}
