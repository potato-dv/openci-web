import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { SignInPage } from "./SignInPage";

describe("SignInPage", () => {
  it("submits credentials to the auth boundary and clears the password", async () => {
    const user = userEvent.setup();
    const onSignIn = vi.fn().mockResolvedValue(undefined);
    render(<SignInPage onSignIn={onSignIn} />);

    await user.type(screen.getByLabelText("Email address"), "user@example.test");
    await user.type(screen.getByLabelText("Password"), "secret-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(onSignIn).toHaveBeenCalledWith("user@example.test", "secret-password");
    expect(screen.getByLabelText("Password")).toHaveValue("");
  });

  it("shows authentication failures without losing the entered email", async () => {
    const user = userEvent.setup();
    const onSignIn = vi.fn().mockRejectedValue(new Error("Invalid credentials"));
    render(<SignInPage onSignIn={onSignIn} />);

    await user.type(screen.getByLabelText("Email address"), "user@example.test");
    await user.type(screen.getByLabelText("Password"), "wrong-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Invalid credentials")).toBeInTheDocument();
    expect(screen.getByLabelText("Email address")).toHaveValue("user@example.test");
  });
});
