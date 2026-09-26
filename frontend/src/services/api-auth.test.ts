// @vitest-environment jsdom
import { afterEach, expect, it } from "vitest";
import { tokenStore } from "./api";

afterEach(() => { tokenStore.clear(); localStorage.clear(); });

it("keeps access tokens in memory instead of browser storage", () => {
  tokenStore.set({ access_token: "temporary", token_type: "bearer" });
  expect(tokenStore.getAccess()).toBe("temporary");
  expect(localStorage.getItem("access_token")).toBeNull();
  expect(localStorage.getItem("refresh_token")).toBeNull();
});
