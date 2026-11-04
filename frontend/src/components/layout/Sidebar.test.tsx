import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import type { User } from "../../types/api";
import { Sidebar } from "./Sidebar";

const supervisor: User = {
  id: 1,
  name: "Test Supervisor",
  email: "supervisor@example.test",
  role: "supervisor",
  is_active: true,
};

describe("Sidebar brand", () => {
  it("uses the Collector wordmark, C mark, and descriptor", () => {
    render(
      <MemoryRouter>
        <Sidebar user={supervisor} />
      </MemoryRouter>,
    );

    const brand = screen.getByRole("link", {
      name: "Collector field operations home",
    });
    expect(brand).toHaveTextContent("Collector");
    expect(brand).toHaveTextContent("Field operations");
    expect(brand.querySelector('img[src="/collector-mark.svg"]')).toHaveAttribute("alt", "");
  });

  it("uses the Collector label in its collapsed-state title", () => {
    render(
      <MemoryRouter>
        <Sidebar user={supervisor} collapsed />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole("link", { name: "Collector field operations home" }),
    ).toHaveAttribute("title", "Collector · Field operations");
  });
});
