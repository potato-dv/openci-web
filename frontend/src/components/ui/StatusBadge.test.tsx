import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("shows the Manila reopen date for a cancelled investigation", () => {
    render(<StatusBadge status="cancelled" reopenOn="2026-11-03" />);

    expect(screen.getByText("cancelled · reopens Nov 3, 2026")).toBeInTheDocument();
  });

  it("keeps the existing status label when no reopen date is present", () => {
    render(<StatusBadge status="in_progress" />);

    expect(screen.getByText("in progress")).toBeInTheDocument();
  });
});
