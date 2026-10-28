import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { ConfirmDialog, FormField, Tabs } from "./Primitives";
it("associates field errors with their input", () => {
  render(<FormField label="Latitude" error="Enter a valid latitude" />);
  expect(screen.getByLabelText("Latitude")).toHaveAttribute(
    "aria-invalid",
    "true",
  );
  expect(screen.getByLabelText("Latitude")).toHaveAccessibleDescription(
    "Enter a valid latitude",
  );
});
it("moves tab selection and focus with the keyboard", async () => {
  function Fixture() {
    const [value, setValue] = useState("first");
    return (
      <Tabs
        label="Test tabs"
        value={value}
        onChange={setValue}
        items={[
          { value: "first", label: "First" },
          { value: "second", label: "Second" },
        ]}
      />
    );
  }
  render(<Fixture />);
  const user = userEvent.setup();
  await user.tab();
  await user.keyboard("{ArrowRight}");
  expect(screen.getByRole("tab", { name: "Second" })).toHaveFocus();
  expect(screen.getByRole("tab", { name: "Second" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
});
it("confirms approval only from the explicit dialog action", async () => {
  const approve = vi.fn();
  render(
    <ConfirmDialog
      open
      title="Approve assignments"
      action="Approve assignments"
      onConfirm={approve}
      onClose={() => {}}
    >
      <p>Review 3 assignments</p>
    </ConfirmDialog>,
  );
  expect(approve).not.toHaveBeenCalled();
  await userEvent.click(
    screen.getByRole("button", { name: "Approve assignments" }),
  );
  expect(approve).toHaveBeenCalledOnce();
});
