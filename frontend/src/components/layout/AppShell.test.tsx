import { render, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";
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

function renderAt(path: string) {
  return render(
    <SessionContext.Provider
      value={{ token: "test-token", user: supervisor, logout() {} }}
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
});
