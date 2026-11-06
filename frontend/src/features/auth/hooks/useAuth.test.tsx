import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { User } from "@/types/api";

const authMocks = vi.hoisted(() => ({
  getProfile: vi.fn(),
  login: vi.fn(),
  accessTokenSubject: vi.fn(),
  clearCurrentAccessToken: vi.fn(),
  refreshAccessToken: vi.fn(),
  requestJson: vi.fn(),
  setCurrentAccessToken: vi.fn(),
  subscribeToReauthenticationRequired: vi.fn(),
  logoutRemoteSession: vi.fn(),
  reauthListener: null as null | ((detail: { code: string; remote?: boolean }) => void),
}));

vi.mock("@/features/auth/api", () => ({
  getProfile: authMocks.getProfile,
  login: authMocks.login,
}));

vi.mock("@/services/http", () => ({
  accessTokenSubject: authMocks.accessTokenSubject,
  clearCurrentAccessToken: authMocks.clearCurrentAccessToken,
  refreshAccessToken: authMocks.refreshAccessToken,
  requestJson: authMocks.requestJson,
  setCurrentAccessToken: authMocks.setCurrentAccessToken,
  subscribeToReauthenticationRequired: authMocks.subscribeToReauthenticationRequired,
  logoutRemoteSession: authMocks.logoutRemoteSession,
}));

import { useAuth } from "./useAuth";

const agent: User = {
  id: 7,
  name: "Test Agent",
  email: "agent@example.test",
  role: "agent",
  is_active: true,
};

const activityEventTypes = [
  "click",
  "keydown",
  "scroll",
  "touchstart",
  "pointerdown",
  "dragstart",
];

let currentTime: number;
let setVisibilityState: (state: DocumentVisibilityState) => void;

beforeEach(() => {
  currentTime = 1_000_000;
  vi.spyOn(Date, "now").mockImplementation(() => currentTime);
  let visibilityState: DocumentVisibilityState = "visible";
  vi.spyOn(document, "visibilityState", "get").mockImplementation(() => visibilityState);
  setVisibilityState = (state) => {
    visibilityState = state;
  };

  authMocks.getProfile.mockReset().mockResolvedValue(agent);
  authMocks.login.mockReset();
  authMocks.accessTokenSubject.mockReset().mockReturnValue(agent.id);
  authMocks.clearCurrentAccessToken.mockReset();
  authMocks.refreshAccessToken.mockReset().mockResolvedValue("access-token");
  authMocks.requestJson.mockReset().mockResolvedValue(undefined);
  authMocks.setCurrentAccessToken.mockReset();
  authMocks.logoutRemoteSession.mockReset();
  authMocks.reauthListener = null;
  authMocks.subscribeToReauthenticationRequired.mockReset().mockImplementation((listener) => {
    authMocks.reauthListener = listener;
    return () => {
      if (authMocks.reauthListener === listener) authMocks.reauthListener = null;
    };
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

async function renderAuthenticatedHook() {
  const view = renderHook(() => useAuth());
  await waitFor(() => expect(view.result.current.user?.id).toBe(agent.id));
  return view;
}

function dispatchActivity(type: string, target: EventTarget = document.body) {
  const event = type === "click"
    ? new MouseEvent(type, { bubbles: true })
    : type === "keydown"
      ? new KeyboardEvent(type, { bubbles: true, key: "a" })
      : new Event(type, { bubbles: type !== "scroll" });
  act(() => target.dispatchEvent(event));
}

describe("authenticated user activity tracking", () => {
  it("records clicks, keyboard, nested scrolling, touch, pointer, and drag activity", async () => {
    const { unmount } = await renderAuthenticatedHook();
    const scrollArea = document.createElement("div");
    document.body.appendChild(scrollArea);

    for (const [index, eventType] of activityEventTypes.entries()) {
      currentTime += 60_001;
      dispatchActivity(eventType, eventType === "scroll" ? scrollArea : document.body);
      expect(authMocks.requestJson).toHaveBeenCalledTimes(index + 1);
      expect(authMocks.requestJson).toHaveBeenLastCalledWith("/users/activity", {
        method: "POST",
        token: "access-token",
      });
    }

    scrollArea.remove();
    unmount();
  });

  it("throttles activity requests and ignores passive mouse movement", async () => {
    const { unmount } = await renderAuthenticatedHook();

    currentTime += 60_001;
    dispatchActivity("scroll");
    currentTime += 30_000;
    dispatchActivity("pointerdown");
    expect(authMocks.requestJson).toHaveBeenCalledTimes(1);

    currentTime += 30_001;
    dispatchActivity("keydown");
    currentTime += 60_001;
    dispatchActivity("mousemove");
    expect(authMocks.requestJson).toHaveBeenCalledTimes(2);

    unmount();
  });

  it("does not report activity while hidden, then resumes when visible", async () => {
    const { unmount } = await renderAuthenticatedHook();
    currentTime += 60_001;

    setVisibilityState("hidden");
    dispatchActivity("scroll");
    expect(authMocks.requestJson).not.toHaveBeenCalled();

    setVisibilityState("visible");
    dispatchActivity("pointerdown");
    expect(authMocks.requestJson).toHaveBeenCalledTimes(1);
    unmount();
  });

  it("removes all activity listeners on unmount", async () => {
    const addListener = vi.spyOn(document, "addEventListener");
    const removeListener = vi.spyOn(document, "removeEventListener");
    const { unmount } = await renderAuthenticatedHook();

    const registrations = addListener.mock.calls.filter(([type]) =>
      activityEventTypes.includes(String(type)),
    );
    expect(registrations.map(([type]) => String(type)).sort()).toEqual(
      [...activityEventTypes].sort(),
    );
    expect(registrations.find(([type]) => type === "scroll")?.[2]).toMatchObject({
      capture: true,
      passive: true,
    });

    removeListener.mockClear();
    unmount();

    for (const [type, listener, options] of registrations) {
      expect(removeListener).toHaveBeenCalledWith(type, listener, options);
    }

    currentTime += 60_001;
    for (const eventType of activityEventTypes) dispatchActivity(eventType);
    expect(authMocks.requestJson).not.toHaveBeenCalled();
  });
});
