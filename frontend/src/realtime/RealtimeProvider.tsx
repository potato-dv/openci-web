import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PropsWithChildren,
} from "react";
import {
  getCurrentAccessToken,
  realtimeWebSocketUrl,
  refreshAccessToken,
} from "@/services/http";
import { RealtimeContext, type RealtimeContextValue } from "./RealtimeContext";
import {
  resourceKeysForEvent,
  subscriptionScopeForResource,
  type RealtimeNotification,
  type ResourceInvalidator,
} from "./resourceMap";

type Props = PropsWithChildren<{
  token: string;
  userId: number;
  role: string;
  enabled: boolean;
  onPermissionsChanged?: () => void | Promise<void>;
}>;

const HEARTBEAT_MS = 25_000;
const INITIAL_RECONNECT_MS = 500;
const MAX_RECONNECT_MS = 30_000;
const INVALIDATION_COALESCE_MS = 100;

function tokenExpiryMs(token: string): number | null {
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    const base64 = payload.replaceAll("-", "+").replaceAll("_", "/");
    const claims = JSON.parse(atob(base64.padEnd(Math.ceil(base64.length / 4) * 4, "="))) as { exp?: unknown };
    return typeof claims.exp === "number" ? claims.exp * 1000 : null;
  } catch {
    return null;
  }
}

function currentToken(fallback: string) {
  return getCurrentAccessToken() || fallback;
}

export function RealtimeProvider({
  token,
  userId,
  role,
  enabled,
  onPermissionsChanged,
  children,
}: Props) {
  const listeners = useRef(new Map<string, Set<ResourceInvalidator>>());
  const pendingInvalidators = useRef(new Set<ResourceInvalidator>());
  const pendingResourceKeys = useRef(new Set<string>());
  const seenEventIds = useRef(new Set<string>());
  const invalidationTimer = useRef<number | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const socketToken = useRef("");
  const authenticatedOnce = useRef(false);
  const reconnectTimer = useRef<number | null>(null);
  const refreshTimer = useRef<number | null>(null);
  const heartbeatTimer = useRef<number | null>(null);
  const reconnectAttempt = useRef(0);
  const stopped = useRef(false);
  const [connected, setConnected] = useState(false);
  const permissionHandler = useRef(onPermissionsChanged);
  permissionHandler.current = onPermissionsChanged;

  const flushInvalidators = useCallback(() => {
    invalidationTimer.current = null;
    const callbacks = [...pendingInvalidators.current];
    pendingInvalidators.current.clear();
    callbacks.forEach((callback) => callback());
  }, []);

  const invalidateKeys = useCallback((keys: Iterable<string>) => {
    const requested = [...keys];
    if (document.visibilityState === "hidden") {
      requested.forEach((key) => pendingResourceKeys.current.add(key));
      return;
    }
    for (const key of requested) {
      for (const callback of listeners.current.get(key) ?? []) {
        pendingInvalidators.current.add(callback);
      }
    }
    if (pendingInvalidators.current.size && invalidationTimer.current === null) {
      invalidationTimer.current = window.setTimeout(flushInvalidators, INVALIDATION_COALESCE_MS);
    }
  }, [flushInvalidators]);

  const subscribeResources = useCallback<RealtimeContextValue["subscribeResources"]>(
    (keys, invalidator) => {
      const normalized = new Set(keys.filter(Boolean));
      for (const key of normalized) {
        const current = listeners.current.get(key) ?? new Set<ResourceInvalidator>();
        current.add(invalidator);
        listeners.current.set(key, current);
      }
      const scopes = [...new Set([...normalized].map(subscriptionScopeForResource).filter((scope): scope is string => Boolean(scope)))];
      if (scopes.length && typeof WebSocket !== "undefined" && socketRef.current?.readyState === WebSocket.OPEN) {
        socketRef.current.send(JSON.stringify({ type: "subscribe", scopes }));
      }
      return () => {
        for (const key of normalized) {
          const current = listeners.current.get(key);
          current?.delete(invalidator);
          if (current?.size === 0) listeners.current.delete(key);
        }
        pendingInvalidators.current.delete(invalidator);
        const remainingScopes = new Set(
          [...listeners.current.keys()]
            .map(subscriptionScopeForResource)
            .filter((scope): scope is string => Boolean(scope)),
        );
        const removedScopes = scopes.filter((scope) => !remainingScopes.has(scope));
        if (removedScopes.length && typeof WebSocket !== "undefined" && socketRef.current?.readyState === WebSocket.OPEN) {
          socketRef.current.send(JSON.stringify({ type: "unsubscribe", scopes: removedScopes }));
        }
      };
    },
    [],
  );

  useEffect(() => {
    if (!enabled || !token || typeof WebSocket === "undefined") {
      setConnected(false);
      socketRef.current?.close(1000, "session_closed");
      socketRef.current = null;
      return;
    }

    stopped.current = false;
    const activeScopes = () => [...new Set(
      ["me", ...[...listeners.current.keys()].map(subscriptionScopeForResource)]
        .filter((scope): scope is string => Boolean(scope)),
    )];

    const stopTimers = () => {
      if (heartbeatTimer.current !== null) window.clearInterval(heartbeatTimer.current);
      if (refreshTimer.current !== null) window.clearTimeout(refreshTimer.current);
      heartbeatTimer.current = null;
      refreshTimer.current = null;
    };

    const scheduleRefresh = (activeSocket: WebSocket, activeToken: string) => {
      if (refreshTimer.current !== null) window.clearTimeout(refreshTimer.current);
      const expiry = tokenExpiryMs(activeToken);
      if (expiry === null) return;
      const wait = Math.max(1_000, expiry - Date.now() - 60_000);
      refreshTimer.current = window.setTimeout(() => {
        void refreshAccessToken()
          .then((nextToken) => {
            if (stopped.current || socketRef.current !== activeSocket) return;
            socketToken.current = nextToken;
            if (activeSocket.readyState === WebSocket.OPEN) {
              activeSocket.send(JSON.stringify({ type: "reauth", token: nextToken }));
            }
            scheduleRefresh(activeSocket, nextToken);
          })
          .catch(() => {
            if (!stopped.current) {
              refreshTimer.current = window.setTimeout(() => scheduleRefresh(activeSocket, currentToken(token)), 10_000);
            }
          });
      }, wait);
    };

    const connect = () => {
      if (stopped.current || document.visibilityState === "hidden") return;
      if (
        socketRef.current?.readyState === WebSocket.CONNECTING ||
        socketRef.current?.readyState === WebSocket.OPEN
      ) return;
      let activeSocket: WebSocket;
      try {
        activeSocket = new WebSocket(realtimeWebSocketUrl());
      } catch {
        scheduleReconnect();
        return;
      }
      socketRef.current = activeSocket;
      let didAuthenticate = false;

      activeSocket.onopen = () => {
        void (async () => {
          let freshToken = currentToken(token);
          const expiresAt = tokenExpiryMs(freshToken);
          if (expiresAt !== null && expiresAt <= Date.now() + 2_000) {
            try {
              freshToken = await refreshAccessToken();
            } catch {
              activeSocket.close(4401, "session_expired");
              return;
            }
          }
          if (stopped.current || socketRef.current !== activeSocket) return;
          socketToken.current = freshToken;
          activeSocket.send(JSON.stringify({
            type: "auth",
            token: freshToken,
            subscriptions: activeScopes(),
          }));
          heartbeatTimer.current = window.setInterval(() => {
            if (activeSocket.readyState !== WebSocket.OPEN) return;
            activeSocket.send(JSON.stringify({ type: "ping", timestamp: Date.now() }));
            const latestToken = currentToken(token);
            if (latestToken !== socketToken.current) {
              socketToken.current = latestToken;
              activeSocket.send(JSON.stringify({ type: "reauth", token: latestToken }));
              scheduleRefresh(activeSocket, latestToken);
            }
          }, HEARTBEAT_MS);
          scheduleRefresh(activeSocket, freshToken);
        })();
      };

      activeSocket.onmessage = (message) => {
        let frame: Record<string, unknown>;
        try {
          frame = JSON.parse(String(message.data)) as Record<string, unknown>;
        } catch {
          return;
        }
        if (frame.type === "authenticated") {
          setConnected(true);
          reconnectAttempt.current = 0;
          if (!didAuthenticate) {
            didAuthenticate = true;
            if (authenticatedOnce.current) invalidateKeys(listeners.current.keys());
            authenticatedOnce.current = true;
          }
          return;
        }
        if (frame.type === "event" && typeof frame.name === "string") {
          const notification = frame as unknown as RealtimeNotification;
          if (seenEventIds.current.has(notification.event_id)) return;
          seenEventIds.current.add(notification.event_id);
          if (seenEventIds.current.size > 512) {
            const oldest = seenEventIds.current.values().next().value;
            if (oldest) seenEventIds.current.delete(oldest);
          }
          invalidateKeys(resourceKeysForEvent(notification));
          if (frame.name === "user.permissions_changed" && frame.entity_id === userId) {
            window.dispatchEvent(new CustomEvent("openci:permissions-changed"));
            void permissionHandler.current?.();
          }
          return;
        }
        if (frame.type === "resync") {
          invalidateKeys(listeners.current.keys());
          return;
        }
        if (frame.type === "reauth_required") {
          void refreshAccessToken()
            .then((nextToken) => activeSocket.send(JSON.stringify({ type: "reauth", token: nextToken })))
            .catch(() => activeSocket.close(4401, "session_revoked"));
        }
      };

      activeSocket.onerror = () => {
        // onclose owns reconnect scheduling; an error event carries no useful detail.
      };

      activeSocket.onclose = (event) => {
        stopTimers();
        if (socketRef.current === activeSocket) socketRef.current = null;
        setConnected(false);
        if (event.code === 4403 && event.reason !== "origin_not_allowed") {
          window.dispatchEvent(new CustomEvent("openci:permissions-changed"));
          void permissionHandler.current?.();
        }
        if (event.code === 4401) {
          window.dispatchEvent(new CustomEvent("openci:reauth-required", {
            detail: { code: event.reason || "session_revoked" },
          }));
        }
        if (event.code === 4403 && event.reason === "origin_not_allowed") {
          stopped.current = true;
        } else {
          scheduleReconnect();
        }
      };
    };

    const scheduleReconnect = () => {
      if (stopped.current || document.visibilityState === "hidden" || reconnectTimer.current !== null) return;
      const base = Math.min(MAX_RECONNECT_MS, INITIAL_RECONNECT_MS * 2 ** reconnectAttempt.current++);
      const jittered = Math.round(base * (0.8 + Math.random() * 0.4));
      reconnectTimer.current = window.setTimeout(() => {
        reconnectTimer.current = null;
        connect();
      }, jittered);
    };

    const onVisibility = () => {
      if (document.visibilityState !== "visible") return;
      if (pendingResourceKeys.current.size) {
        const pendingKeys = [...pendingResourceKeys.current];
        pendingResourceKeys.current.clear();
        invalidateKeys(pendingKeys);
      }
      if (reconnectTimer.current !== null) {
        window.clearTimeout(reconnectTimer.current);
        reconnectTimer.current = null;
      }
      connect();
    };
    const onNetworkOnline = () => {
      if (socketRef.current?.readyState !== WebSocket.OPEN) {
        if (reconnectTimer.current !== null) window.clearTimeout(reconnectTimer.current);
        reconnectTimer.current = null;
        connect();
      }
    };

    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("online", onNetworkOnline);
    // StrictMode immediately runs effect setup/cleanup once in development.
    // Defer opening until that cleanup can cancel the throwaway mount.
    const initialConnectTimer = window.setTimeout(connect, 0);

    return () => {
      stopped.current = true;
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("online", onNetworkOnline);
      window.clearTimeout(initialConnectTimer);
      if (reconnectTimer.current !== null) window.clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
      stopTimers();
      const activeSocket = socketRef.current;
      socketRef.current = null;
      setConnected(false);
      if (activeSocket && activeSocket.readyState < WebSocket.CLOSING) {
        activeSocket.close(1000, "session_closed");
      }
    };
  }, [enabled, invalidateKeys, role, token, userId]);

  const value = useMemo<RealtimeContextValue>(
    () => ({ subscribeResources, connected }),
    [connected, subscribeResources],
  );

  return (
    <RealtimeContext.Provider value={value}>
      {children}
    </RealtimeContext.Provider>
  );
}
