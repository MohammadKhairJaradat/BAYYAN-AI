// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { api, refreshAccessToken, tokenStore } from "../services/api";
import { AuthProvider } from "./AuthContext";
import { useAuth } from "./hooks";

vi.mock("../services/api", () => ({
  api: { get: vi.fn(), post: vi.fn() },
  refreshAccessToken: vi.fn(),
  tokenStore: { set: vi.fn(), clear: vi.fn() },
}));

function Probe() {
  const { user, loading, logout } = useAuth();
  return <div>
    <span>{loading ? "Loading" : user?.name ?? "Signed out"}</span>
    <button onClick={() => void logout()}>Sign out</button>
  </div>;
}

afterEach(() => { cleanup(); vi.resetAllMocks(); });

it("restores an existing session by rotating the cookie and loading the user", async () => {
  vi.mocked(refreshAccessToken).mockResolvedValue("new-access");
  vi.mocked(api.get).mockResolvedValue({ data: { id: "1", name: "Mohammad" } });
  vi.mocked(api.post).mockResolvedValue({});
  render(<AuthProvider><Probe /></AuthProvider>);
  expect(screen.getByText("Loading")).toBeTruthy();
  expect(await screen.findByText("Mohammad")).toBeTruthy();
  expect(api.get).toHaveBeenCalledWith("/auth/me");
  fireEvent.click(screen.getByText("Sign out"));
  await waitFor(() => expect(api.post).toHaveBeenCalledWith("/auth/logout"));
  await waitFor(() => expect(screen.getByText("Signed out")).toBeTruthy());
  expect(tokenStore.clear).toHaveBeenCalled();
});
