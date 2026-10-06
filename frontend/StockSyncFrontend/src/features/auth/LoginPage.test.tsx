import { beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { LoginPage } from "./LoginPage";
import { RequireAuth } from "../../auth/RequireAuth";
import { storageKeys } from "../../lib/storage";
import { renderWithProviders } from "../../test/utils";

function renderLoginFlow() {
  return renderWithProviders(
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route path="/products/new" element={<p>Formulário de produto</p>} />
      </Route>
      <Route path="/" element={<p>Dashboard</p>} />
    </Routes>,
    { route: "/login" }
  );
}

describe("LoginPage", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("recusa credenciais vazias", async () => {
    const { user } = renderLoginFlow();

    await user.click(screen.getByRole("button", { name: "Entrar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Informe o nome de usuário."
    );
  });

  it("avisa quando a senha não é informada", async () => {
    const { user } = renderLoginFlow();

    await user.type(screen.getByLabelText("Username"), "amoras");
    await user.click(screen.getByRole("button", { name: "Entrar" }));

    expect(await screen.findByText("Informe a senha.")).toBeInTheDocument();
  });

  it("persiste a sessão ao entrar", async () => {
    const { user } = renderLoginFlow();

    await user.type(screen.getByLabelText("Username"), "amoras");
    await user.type(screen.getByLabelText("Password"), "123456");
    await user.click(screen.getByRole("button", { name: "Entrar" }));

    await waitFor(() => {
      const stored = window.localStorage.getItem(storageKeys.session);
      expect(stored).not.toBeNull();
      expect(JSON.parse(stored ?? "{}").username).toBe("amoras");
    });
  });

  /**
   * Reproduz o fluxo da Imagem 3: deslogado em `/products/new`, RequireAuth
   * redireciona para o login guardando o destino; após autenticar, o usuário
   * deve voltar ao formulário.
   */
  it("retorna à rota original após o login", async () => {
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
    expect(screen.getByLabelText("Username")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Username"), "amoras");
    await user.type(screen.getByLabelText("Password"), "123456");
    await user.click(screen.getByRole("button", { name: "Entrar" }));

    expect(
      await screen.findByText("Formulário de produto")
    ).toBeInTheDocument();
  });
});