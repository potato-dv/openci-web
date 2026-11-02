import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { User } from "@/types/api";

const mockAuth = vi.hoisted(() => ({ value: null as null | Record<string, unknown> }));

vi.mock("@/features/auth/hooks/useAuth", () => ({
  useAuth: () => mockAuth.value,
}));

vi.mock("@/app/router", async () => {
  const React = await import("react");
  return {
    AppRoutes: function MockAppRoutes() {
      const [draft, setDraft] = React.useState("");
      return (
        <div>
          <label>
            Unsaved report draft
            <input value={draft} onChange={(event) => setDraft(event.target.value)} />
          </label>
        </div>
      );
    },
  };
});

import App from "@/App";

const agent: User = {
  id: 7,
  name: "Test Agent",
  email: "agent@example.test",
  role: "agent",
  is_active: true,
};

function authState(overrides: Record<string, unknown> = {}) {
  return {
    accessToken: "initial-access-token",
    user: agent,
    isInitializing: false,
    reauthRequired: false,
    login: vi.fn(),
    reauthenticate: vi.fn().mockResolvedValue(undefined),
    logout: vi.fn(),
    ...overrides,
  };
}

describe("reauthentication overlay", () => {
  beforeEach(() => {
    mockAuth.value = authState();
  });

  it("keeps the mounted report draft while the same user signs in again", () => {
    const view = render(<App />);
    const draft = screen.getByLabelText("Unsaved report draft");
    fireEvent.change(draft, { target: { value: "Field notes not saved yet" } });

    mockAuth.value = authState({ reauthRequired: true });
    view.rerender(<App />);
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    mockAuth.value = authState({ accessToken: "rotated-access-token" });
    view.rerender(<App />);
    expect(screen.getByLabelText("Unsaved report draft")).toHaveValue("Field notes not saved yet");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("remounts the workspace when a different account signs in", () => {
    const view = render(<App />);
    fireEvent.change(screen.getByLabelText("Unsaved report draft"), {
      target: { value: "Previous account notes" },
    });

    mockAuth.value = authState({
      user: { ...agent, id: 8, email: "other@example.test" },
      accessToken: "other-account-token",
    });
    view.rerender(<App />);
    expect(screen.getByLabelText("Unsaved report draft")).toHaveValue("");
  });
});
