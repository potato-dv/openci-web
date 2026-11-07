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

  it("shows a binary history choice and saves its per-Agent override", async () => {
    renderPage();

    expect(await screen.findByRole("radio", { name: "Deny" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Allow" })).not.toBeChecked();
    expect(screen.getByText("Agent: Agent Example")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Effective access" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Agent Example cannot view their investigation history.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Visit reporting")).toBeInTheDocument();
    expect(screen.getByText("Required workflows")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: "Allow" }));
    fireEvent.click(screen.getByRole("button", { name: "Save permissions" }));

    await waitFor(() =>
      expect(mocks.saveAgentPermissionState).toHaveBeenCalledOnce(),
    );
    expect(mocks.saveAgentPermissionState).toHaveBeenCalledWith(
      "token",
      7,
      expect.objectContaining({
        "investigation.view_own_history": "allow",
      }),
    );
    expect(await screen.findByRole("status")).toHaveTextContent(
      /permissions saved/i,
    );
    expect(
      screen.getByText("Agent Example can view their investigation history."),
    ).toBeInTheDocument();
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

    expect(await screen.findByRole("radio", { name: "Allow" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Deny" })).not.toBeChecked();
    expect(
      screen.getByText("Agent Example can view their investigation history."),
    ).toBeInTheDocument();
  });

  it("shows override and effective-value transitions in the history", async () => {
    mocks.getAgentPermissionHistory.mockResolvedValue({
      items: [
        {
          id: 3,
          actor_name: "Administrator",
          created_at: "2026-11-07T08:00:00Z",
          old_overrides: { "investigation.request_revisit": "inherit" },
          new_overrides: { "investigation.request_revisit": "deny" },
          old_effective: { "investigation.request_revisit": true },
          new_effective: { "investigation.request_revisit": false },
        },
      ],
      total: 1,
      limit: 50,
      offset: 0,
    });

    renderPage();

    expect(
      await screen.findByText(
        /Request a revisit: Use default → Deny · effective access Allowed → Denied/,
      ),
    ).toBeInTheDocument();
  });

  it("keeps audit entries from the previous individual history permissions readable", async () => {
    mocks.getAgentPermissionHistory.mockResolvedValue({
      items: [
        {
          id: 4,
          actor_name: "Administrator",
          created_at: "2026-11-07T08:00:00Z",
          old_overrides: { "investigation.view_own_report_history": "allow" },
          new_overrides: { "investigation.view_own_report_history": "deny" },
          old_effective: { "investigation.view_own_report_history": true },
          new_effective: { "investigation.view_own_report_history": false },
        },
      ],
      total: 1,
      limit: 50,
      offset: 0,
    });

    renderPage();

    expect(
      await screen.findByText(/Legacy View own report history: Allow → Deny/),
    ).toBeInTheDocument();
  });
});
