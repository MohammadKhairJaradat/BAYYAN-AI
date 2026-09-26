// @vitest-environment jsdom
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { UserAvatar } from "./avatar";

describe("UserAvatar", () => {
  it("retries a new avatar URL after the previous image fails", () => {
    const user = { name: "ليلى", username: "layla", avatar_url: "/old.png" };
    const view = render(<UserAvatar user={user} />);
    fireEvent.error(screen.getByAltText("User avatar"));
    expect(screen.queryByAltText("User avatar")).toBeNull();
    expect(screen.getByText("ل")).toBeTruthy();

    view.rerender(<UserAvatar user={{ ...user, avatar_url: "/new.png" }} />);
    expect(screen.getByAltText("User avatar").getAttribute("src")).toBe("/new.png");
  });
});
