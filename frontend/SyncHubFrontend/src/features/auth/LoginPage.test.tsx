import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { LoginPage } from "./LoginPage";
import { RequireAuth } from "../../auth/RequireAuth";
import { renderWithProviders } from "../../test/utils";
import { authClient } from "../../lib/api/auth-client";
import { paths } from "../../routes/paths";

/**
 * A sessão vive em cookie HTTP-only: o estado do usuário vem de
 * `authClient.me()` (AuthProvider) e `authClient.login()` preenche o contexto
 * após autenticar. Os mocks espelham esse fluxo.
 */
vi.mock("../../lib/api/auth-client", () => ({
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

function renderLoginFlow(extraRoutes: React.ReactNode = null) {
  return renderWithProviders(
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      {extraRoutes}
      <Route element={<RequireAuth />}>
        <Route path="/products/new" element={<p>Formulário de produto</p>} />
      </Route>
      <Route path={paths.dashboard} element={<p>Dashboard</p>} />
    </Routes>,
    { route: "/login" }
  );
}

describe("LoginPage", () => {
  beforeEach(() => {
    // Visitante: sem cookie de sessão, /me rejeita.
    vi.mocked(authClient.me).mockRejectedValue(new Error("Not authenticated"));
    vi.mocked(authClient.login).mockReset();
  });

  it("recusa credenciais vazias", async () => {
    const { user } = renderLoginFlow();

    await user.click(await screen.findByRole("button", { name: "Entrar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Informe o e-mail."
    );
  });

  it("avisa quando a senha não é informada", async () => {
    const { user } = renderLoginFlow();

    await user.type(
      await screen.findByLabelText("E-mail"),
      "amoras@example.com"
    );
    await user.click(screen.getByRole("button", { name: "Entrar" }));

    expect(await screen.findByText("Informe a senha.")).toBeInTheDocument();
  });

  it("autentica e leva ao dashboard", async () => {
    vi.mocked(authClient.login).mockResolvedValue(authenticatedUser);
    const { user } = renderLoginFlow();

    await user.type(
      await screen.findByLabelText("E-mail"),
      "amoras@example.com"
    );
    await user.type(screen.getByLabelText("Senha"), "123456");
    await user.click(screen.getByRole("button", { name: "Entrar" }));

    expect(await screen.findByText("Dashboard")).toBeInTheDocument();
    expect(authClient.login).toHaveBeenCalledWith({
      email: "amoras@example.com",
      password: "123456",
    });
  });

  /**
   * Reproduz o fluxo da Imagem 3: deslogado em `/products/new`, RequireAuth
   * redireciona para o login guardando o destino; após autenticar, o usuário
   * deve voltar ao formulário.
   */
  it("retorna à rota original após o login", async () => {
    vi.mocked(authClient.login).mockResolvedValue(authenticatedUser);
    const { user } = renderWithProviders(
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<RequireAuth />}>
          <Route
            path="/products/new"
            element={<p>Formulário de produto</p>}
          />
        </Route>
      </Routes>,
      { route: "/products/new" }
    );

    // O guard redirecionou para o login.
    expect(await screen.findByLabelText("E-mail")).toBeInTheDocument();

    await user.type(screen.getByLabelText("E-mail"), "amoras@example.com");
    await user.type(screen.getByLabelText("Senha"), "123456");
    await user.click(screen.getByRole("button", { name: "Entrar" }));

    expect(
      await screen.findByText("Formulário de produto")
    ).toBeInTheDocument();
  });
});
