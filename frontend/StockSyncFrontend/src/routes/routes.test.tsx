import { beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { AppRoutes } from "./index";
import { renderWithProviders } from "../test/utils";
import { storageKeys } from "../lib/storage";
import { clearPersisted } from "../mock/handlers";
import { resetDatabase } from "../mock/db";

function renderApp(route: string) {
  return renderWithProviders(<AppRoutes />, { route });
}

// O `db` do mock é um singleton de módulo; com `isolate: false` no Vitest ele
// é compartilhado entre arquivos de teste, então cada caso recomeça do seed.
beforeEach(() => {
  resetDatabase();
  clearPersisted();
});

describe("rotas da aplicação", () => {
  it("exibe o dashboard para visitante deslogado", async () => {
    renderApp("/");

    expect(
      await screen.findByText("Aqui está o resumo das suas vendas hoje")
    ).toBeInTheDocument();
    expect(screen.getByText("Bem-vindo de volta!")).toBeInTheDocument();
    // Avatar "G" de visitante no rodapé da sidebar.
    expect(screen.getAllByText("G").length).toBeGreaterThan(0);
  });

  it("mostra o nome do usuário no dashboard autenticado", async () => {
    window.localStorage.setItem(
      storageKeys.session,
      JSON.stringify({ id: 1, username: "amoras", email: "" })
    );

    renderApp("/");

    expect(
      await screen.findByText("Bem-vindo de volta, amoras!")
    ).toBeInTheDocument();
    expect(screen.getAllByText("A").length).toBeGreaterThan(0);
  });

  it("contabiliza os SKUs semeados no dashboard", async () => {
    renderApp("/");

    await waitFor(() => {
      expect(screen.getByText("Total de SKUs.")).toBeInTheDocument();
    });
  });

  it("libera a listagem de produtos sem sessão", async () => {
    renderApp("/products");

    expect(
      await screen.findByRole("heading", { name: "Produtos" })
    ).toBeInTheDocument();
    // O mock resolve com atraso artificial; a linha só existe após a query.
    expect(await screen.findByText("rafael")).toBeInTheDocument();
    expect(screen.getByText("R$ 10,00")).toBeInTheDocument();
  });

  it("exibe o formulário de login em /login", async () => {
    renderApp("/login");

    expect(await screen.findByLabelText("Username")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
  });

  it("protege a criação de produto sem sessão", async () => {
    renderApp("/products/new");

    expect(await screen.findByLabelText("Username")).toBeInTheDocument();
  });

  it("protege o perfil sem sessão", async () => {
    renderApp("/profile");

    expect(await screen.findByLabelText("Username")).toBeInTheDocument();
  });

  it("libera o detalhe do produto sem sessão", async () => {
    renderApp("/products/1");

    expect(await screen.findByText("R$ 10,00")).toBeInTheDocument();
    // A seção de anúncios só resolve depois da própria query.
    expect(
      await screen.findByText("Nenhum anúncio vinculado.")
    ).toBeInTheDocument();
  });

  it("redireciona rota desconhecida para o dashboard", async () => {
    renderApp("/rota-que-nao-existe");

    expect(
      await screen.findByText("Aqui está o resumo das suas vendas hoje")
    ).toBeInTheDocument();
  });

  it("mantém a sidebar e o topo em todas as telas", async () => {
    const { container } = renderApp("/");

    expect(await screen.findByLabelText("Navegação principal")).toBeInTheDocument();
    expect(container.querySelector("header")).not.toBeNull();
  });
});