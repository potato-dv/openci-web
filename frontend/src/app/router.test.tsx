import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { expect, it, vi } from "vitest";
import { SessionContext } from "./session";
import { ProtectedRoute, AppRoutes } from "./router";
import { Sidebar } from "../components/layout/Sidebar";
const agent = {
  id: 1,
  name: "Fictional Agent",
  email: "agent@example.test",
  role: "agent" as const,
  is_active: true,
};
it("returns a 403 for an unauthorized direct route", () => {
  render(
    <MemoryRouter>
      <SessionContext.Provider
        value={{ user: agent, token: "test", logout() {} }}
      >
        <ProtectedRoute roles={["admin"]}>
          <p>Secret content</p>
        </ProtectedRoute>
      </SessionContext.Provider>
    </MemoryRouter>,
  );
  expect(screen.getByText("403 · Access restricted")).toBeInTheDocument();
  expect(screen.queryByText("Secret content")).not.toBeInTheDocument();
});
it("hides administration and planning navigation from agents", () => {
  render(
    <MemoryRouter>
      <Sidebar user={agent} />
    </MemoryRouter>,
  );
  expect(screen.getByRole("link", { name: "My Route" })).toBeInTheDocument();
  expect(
    screen.queryByRole("link", { name: "User Management" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("link", { name: "Route Planning" }),
  ).not.toBeInTheDocument();
});
it("keeps collapsed navigation labeled without a sidebar account control", () => {
  const toggle = vi.fn();
  render(
    <MemoryRouter>
      <Sidebar user={agent} collapsed onToggleCollapse={toggle} />
    </MemoryRouter>,
  );
  expect(screen.getByRole("link", { name: "My Route" })).toBeInTheDocument();
  const expandControl = screen.getByRole("button", { name: "Expand navigation" });
  expect(expandControl.closest(".sidebar-header")).toBeTruthy();
  expect(
    screen.queryByRole("button", { name: /Account menu for Fictional Agent/ }),
  ).not.toBeInTheDocument();
  fireEvent.click(expandControl);
  expect(toggle).toHaveBeenCalledOnce();
});
it("handles unknown URLs with a not found view", () => {
  render(
    <MemoryRouter initialEntries={["/does-not-exist"]}>
      <SessionContext.Provider
        value={{ user: agent, token: "test", logout() {} }}
      >
        <AppRoutes />
      </SessionContext.Provider>
    </MemoryRouter>,
  );
  expect(screen.getByText("404 · Page not found")).toBeInTheDocument();
});
