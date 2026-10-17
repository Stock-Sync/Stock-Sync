import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { AppRoutes } from "./index";
import { renderWithProviders } from "../test/utils";
import { storageKeys } from "../lib/storage";
import { authClient } from "../lib/api/auth-client";

function renderApp(route: string) {
  return renderWithProviders(<AppRoutes />, { route });
}

// Mock dos clientes de API usados pelas rotas.
vi.mock("../lib/api/catalog-client", () => ({
  catalogClient: {
    listProducts: vi.fn().mockResolvedValue([
      { id: 1, name: "Titulo", description: "produto rafa", created_at: "2026-09-19T13:02:00.000Z", updated_at: "2026-09-19T13:02:00.000Z" },
    ]),
    listSkus: vi.fn().mockResolvedValue([
      { id: 1, product_id: 1, internal_sku: "rafael", price: 10, stock_quantity: 0, created_at: "2026-09-19T13:02:00.000Z", updated_at: "2026-09-19T13:02:00.000Z" },
    ]),
  },
}));

// Mock do auth client para tests.
// Observação: o cliente devolve o usuário direto (não envolto em { user }).
// `me` rejeita por padrão (usuário não autenticado); testes que precisam de
// sessão sobrescrevem com mockResolvedValueOnce.
vi.mock("../lib/api/auth-client", () => ({
  authClient: {
    me: vi.fn().mockRejectedValue(new Error("Not authenticated")),
    login: vi.fn().mockResolvedValue({ id: "1", name: "amoras", email: "amoras@example.com", is_active: true, created_at: new Date().toISOString() }),
    logout: vi.fn().mockResolvedValue({ message: "Logged out" }),
  },
}));

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
    vi.mocked(authClient.me).mockResolvedValueOnce({
      id: "1",
      name: "amoras",
      email: "amoras@example.com",
      is_active: true,
      created_at: new Date().toISOString(),
    });

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
  });

  it("exibe o formulário de login em /login", async () => {
    renderApp("/login");

    expect(await screen.findByLabelText("E-mail")).toBeInTheDocument();
    expect(screen.getByLabelText("Senha")).toBeInTheDocument();
  });

  it("protege a criação de produto sem sessão", async () => {
    renderApp("/products/new");

    expect(await screen.findByLabelText("E-mail")).toBeInTheDocument();
  });

  it("protege o perfil sem sessão", async () => {
    renderApp("/profile");

    expect(await screen.findByLabelText("E-mail")).toBeInTheDocument();
  });

  it("libera o detalhe do produto sem sessão", async () => {
    renderApp("/products/1");

    expect(await screen.findByText("Titulo")).toBeInTheDocument();
    expect(screen.getByText("R$ 10,00")).toBeInTheDocument();
  });

  it("protege a criação de anúncio sem sessão", async () => {
    renderApp("/listings/new");

    expect(await screen.findByLabelText("E-mail")).toBeInTheDocument();
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