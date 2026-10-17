import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AuthProvider } from "../auth/AuthProvider";
import { RequireAuth } from "./RequireAuth";
import { createTestQueryClient } from "../test/utils";
import { QueryClientProvider } from "@tanstack/react-query";
import { authClient } from "../lib/api/auth-client";

// A sessão vive em cookie HTTP-only: o guard depende do estado carregado por
// authClient.me() no AuthProvider, não de localStorage.
vi.mock("../lib/api/auth-client", () => ({
  authClient: {
    me: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    register: vi.fn(),
    refresh: vi.fn(),
  },
}));

const authenticatedUser = {
  id: "1",
  name: "amoras",
  email: "amoras@example.com",
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
};

function renderRoutes(initialEntry: string) {
  const queryClient = createTestQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<p>Tela de login</p>} />
            <Route element={<RequireAuth />}>
              <Route path="/products/new" element={<p>Formulário de produto</p>} />
            </Route>
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("RequireAuth", () => {
  it("leva para o login quando não há sessão", () => {
    vi.mocked(authClient.me).mockRejectedValue(new Error("Not authenticated"));

    renderRoutes("/products/new");

    expect(screen.getByText("Tela de login")).toBeInTheDocument();
    expect(
      screen.queryByText("Formulário de produto")
    ).not.toBeInTheDocument();
  });

  it("libera a rota quando o backend valida a sessão", async () => {
    vi.mocked(authClient.me).mockResolvedValue(authenticatedUser);

    renderRoutes("/products/new");

    expect(await screen.findByText("Formulário de produto")).toBeInTheDocument();
  });
});
