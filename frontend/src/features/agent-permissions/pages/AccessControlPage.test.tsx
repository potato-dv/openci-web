import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SessionContext } from "@/app/session";
import type { AgentPermissionState, User } from "@/types/api";

const mocks = vi.hoisted(() => ({
  getUsers: vi.fn(),
  getAgentPermissionCatalog: vi.fn(),
  getAgentPermissionState: vi.fn(),
  getAgentPermissionHistory: vi.fn(),
  saveAgentPermissionState: vi.fn(),
}));

vi.mock("@/features/users/api", () => ({ getUsers: mocks.getUsers }));
vi.mock("@/features/agent-permissions/api", () => ({
  getAgentPermissionCatalog: mocks.getAgentPermissionCatalog,
  getAgentPermissionState: mocks.getAgentPermissionState,
  getAgentPermissionHistory: mocks.getAgentPermissionHistory,
  saveAgentPermissionState: mocks.saveAgentPermissionState,
}));

import { AccessControlPage } from "./AccessControlPage";

const admin: User = {
  id: 1,
  name: "Admin Example",
  email: "admin@example.test",
  role: "admin",
  is_active: true,
};

const state: AgentPermissionState = {
  agent: { id: 7, name: "Agent Example", is_active: true },
  features: [
    {
      code: "investigation.request_revisit",
      name: "Request a revisit",
      description: "Ask for a correction visit.",
      default_allowed: true,
      override: null,
      effective_allowed: true,
    },
    {
      code: "route.view_own_history",
      name: "View own route history",
      description: "View earlier routes.",
      default_allowed: true,
      override: null,
      effective_allowed: true,
    },
    {
      code: "investigation.view_own_history",
      name: "View own history",
      description:
        "Completed investigations, earlier report versions, and activity.",
      default_allowed: false,
      override: null,
      effective_allowed: false,
    },
  ],
  mandatory_workflows: [
    { name: "Visit reporting", description: "Reports remain required." },
  ],
};

function renderPage() {
  return render(
    <MemoryRouter>
      <SessionContext.Provider
        value={{ user: admin, token: "token", logout() {} }}
      >
        <AccessControlPage />
      </SessionContext.Provider>
    </MemoryRouter>,
  );
}

describe("Agent Access Control page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getUsers.mockResolvedValue([
      {
        ...admin,
        id: 7,
        name: "Agent Example",
        email: "agent@example.test",
        role: "agent",
      },
    ]);
    mocks.getAgentPermissionCatalog.mockResolvedValue({
      features: state.features,
      mandatory_workflows: state.mandatory_workflows,
    });
    mocks.getAgentPermissionState.mockResolvedValue(state);
    mocks.getAgentPermissionHistory.mockResolvedValue({
      items: [],
      total: 0,
      limit: 50,
      offset: 0,
    });
    mocks.saveAgentPermissionState.mockResolvedValue({
      ...state,
      features: state.features.map((feature) =>
        feature.code === "investigation.view_own_history"
          ? { ...feature, override: "allow", effective_allowed: true }
          : feature,
      ),
    });
  });

  it("uses Allow/Deny choices without changing untouched default overrides", async () => {
    renderPage();

    expect(await screen.findByRole("radio", { name: "View own history permission: Deny" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "View own history permission: Allow" })).not.toBeChecked();
    expect(screen.getByRole("radio", { name: "Request a revisit permission: Allow" })).toBeChecked();
    expect(screen.getByLabelText("Agent")).toBeInTheDocument();
    expect(screen.queryByText("Use default")).not.toBeInTheDocument();
    expect(screen.queryByText(/Agent default:/)).not.toBeInTheDocument();
    expect(screen.queryByText("Required workflows")).not.toBeInTheDocument();
    expect(screen.queryByText("Permission history")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: "View own history permission: Allow" }));
    fireEvent.click(screen.getByRole("button", { name: "Save permissions" }));

    await waitFor(() =>
      expect(mocks.saveAgentPermissionState).toHaveBeenCalledOnce(),
    );
    expect(mocks.saveAgentPermissionState).toHaveBeenCalledWith(
      "token",
      7,
      expect.objectContaining({
        "investigation.request_revisit": "inherit",
        "investigation.view_own_history": "allow",
      }),
    );
    expect(await screen.findByRole("status")).toHaveTextContent(/permissions saved/i);
    expect(mocks.getAgentPermissionHistory).not.toHaveBeenCalled();
  });

  it("loads the selected history choice from saved effective permission data", async () => {
    mocks.getAgentPermissionState.mockResolvedValue({
      ...state,
      features: state.features.map((feature) =>
        feature.code === "investigation.view_own_history"
          ? { ...feature, override: "allow", effective_allowed: true }
          : feature,
      ),
    });

    renderPage();

    expect(await screen.findByRole("radio", { name: "View own history permission: Allow" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "View own history permission: Deny" })).not.toBeChecked();
    expect(screen.queryByText("Effective access")).not.toBeInTheDocument();
    expect(mocks.getAgentPermissionHistory).not.toHaveBeenCalled();
  });

  it("preserves unsaved choices when permissions change elsewhere", async () => {
    let now = 1_000;
    vi.spyOn(Date, "now").mockImplementation(() => now);
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      value: "visible",
    });
    renderPage();
    const denyRevisit = await screen.findByRole("radio", { name: "Request a revisit permission: Deny" });
    fireEvent.click(denyRevisit);

    mocks.getAgentPermissionState.mockResolvedValue({
      ...state,
      features: state.features.map((feature) =>
        feature.code === "investigation.view_own_history"
          ? { ...feature, override: "allow", effective_allowed: true }
          : feature,
      ),
    });
    now = 62_000;
    window.dispatchEvent(new Event("focus"));

    expect(await screen.findByText(/permissions changed elsewhere/i)).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Request a revisit permission: Deny" })).toBeChecked();
    expect(screen.getByRole("button", { name: "Save permissions" })).toBeDisabled();
  });
});
