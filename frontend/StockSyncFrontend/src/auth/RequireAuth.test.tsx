import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AuthProvider } from "../auth/AuthProvider";
import { RequireAuth } from "./RequireAuth";
import { createTestQueryClient } from "../test/utils";
import { QueryClientProvider } from "@tanstack/react-query";

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
    renderRoutes("/products/new");

    expect(screen.getByText("Tela de login")).toBeInTheDocument();
    expect(
      screen.queryByText("Formulário de produto")
    ).not.toBeInTheDocument();
  });

  it("libera a rota quando existe sessão no localStorage", () => {
    window.localStorage.setItem(
      "stocksync:session",
      JSON.stringify({ id: 1, username: "amoras", email: "" })
    );

    renderRoutes("/products/new");

    expect(screen.getByText("Formulário de produto")).toBeInTheDocument();
  });
});