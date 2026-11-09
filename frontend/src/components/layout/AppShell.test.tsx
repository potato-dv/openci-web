import { act, render, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { SessionContext } from "../../app/session";
import type { User } from "../../types/api";
import { AppShell } from "./AppShell";

const supervisor: User = {
  id: 1,
  name: "Test Supervisor",
  email: "supervisor@example.test",
  role: "supervisor",
  is_active: true,
};

const agent: User = {
  id: 2,
  name: "Test Agent",
  email: "agent@example.test",
  role: "agent",
  is_active: true,
};

function renderAt(
  path: string,
  user: User = supervisor,
  refreshAgentPermissions?: () => Promise<void>,
) {
  return render(
    <SessionContext.Provider
      value={{ token: "test-token", user, logout() {}, refreshAgentPermissions }}
    >
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/dashboard" element={<div>Dashboard content</div>} />
            <Route
              path="/route-planning"
              element={<div>Route planning content</div>}
            />
          </Route>
        </Routes>
      </MemoryRouter>
    </SessionContext.Provider>,
  );
}

describe("AppShell browser title", () => {
  it("uses Collector on the dashboard title", async () => {
    renderAt("/dashboard");

    await waitFor(() => expect(document.title).toBe("dashboard · Collector"));
  });

  it("uses Collector on the Route Planning title", async () => {
    renderAt("/route-planning");

    await waitFor(() => expect(document.title).toBe("route planning · Collector"));
  });

  it("refreshes Agent permissions on focus without polling", async () => {
    vi.useFakeTimers();
    const refreshAgentPermissions = vi.fn().mockResolvedValue(undefined);

    try {
      renderAt("/dashboard", agent, refreshAgentPermissions);
      expect(refreshAgentPermissions).not.toHaveBeenCalled();

      await vi.advanceTimersByTimeAsync(15_000);
      expect(refreshAgentPermissions).not.toHaveBeenCalled();

      act(() => window.dispatchEvent(new Event("focus")));
      expect(refreshAgentPermissions).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });
});
