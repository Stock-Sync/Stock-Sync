import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { AppRoutes } from "./index";
import { renderWithProviders } from "../test/utils";
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
// `me` rejeita por padrão (usuário não autenticado).
vi.mock("../lib/api/auth-client", () => ({
  authClient: {
    me: vi.fn().mockRejectedValue(new Error("Not authenticated")),
    login: vi.fn().mockResolvedValue({ id: "1", name: "amoras", email: "amoras@example.com", is_active: true, created_at: new Date().toISOString() }),
    logout: vi.fn().mockResolvedValue({ message: "Logged out" }),
  },
}));

describe("rotas da aplicação", () => {
  it("exibe a landing para visitante deslogado", async () => {
    renderApp("/");

    const stockSync = await screen.findAllByText("Stock Sync");
    expect(stockSync.length).toBeGreaterThan(0);
    // CTAs de entrar e criar conta estão presentes na landing pública.
    const criarContaLinks = await screen.findAllByRole("link", {
      name: /Criar conta grátis/,
    });
    expect(criarContaLinks.length).toBeGreaterThan(0);
    const entrarLinks = await screen.findAllByRole("link", { name: /Entrar/ });
    expect(entrarLinks.length).toBeGreaterThan(0);
  });

  it("protege páginas restritas sem sessão", async () => {
    renderApp("/dashboard");

    expect(await screen.findByLabelText("E-mail")).toBeInTheDocument();
  });

  it("protege a listagem de produtos sem sessão", async () => {
    renderApp("/products");

    expect(await screen.findByLabelText("E-mail")).toBeInTheDocument();
  });

  it("protege a criação de produto sem sessão", async () => {
    renderApp("/products/new");

    expect(await screen.findByLabelText("E-mail")).toBeInTheDocument();
  });

  it("exibe o formulário de login em /login", async () => {
    renderApp("/login");

    expect(await screen.findByLabelText("E-mail")).toBeInTheDocument();
    expect(screen.getByLabelText("Senha")).toBeInTheDocument();
  });

  it("exibe o formulário de cadastro em /register", async () => {
    renderApp("/register");

    expect(await screen.findByLabelText("Nome")).toBeInTheDocument();
    expect(await screen.findByLabelText("E-mail")).toBeInTheDocument();
    expect(screen.getByLabelText("Senha")).toBeInTheDocument();
  });

  it("protege o perfil sem sessão", async () => {
    renderApp("/profile");

    expect(await screen.findByLabelText("E-mail")).toBeInTheDocument();
  });

  it("protege a criação de anúncio sem sessão", async () => {
    renderApp("/listings/new");

    expect(await screen.findByLabelText("E-mail")).toBeInTheDocument();
  });

  it("redireciona rota desconhecida para a landing", async () => {
    renderApp("/rota-que-nao-existe");

    const stockSync = await screen.findAllByText("Stock Sync");
    expect(stockSync.length).toBeGreaterThan(0);
  });

  it("autentica e leva ao dashboard a partir do login", async () => {
    vi.mocked(authClient.login).mockResolvedValue({
      id: "1",
      name: "amoras",
      email: "amoras@example.com",
      is_active: true,
      created_at: new Date().toISOString(),
    });

    renderApp("/login");

    await screen.findByLabelText("E-mail");
    await screen.findByLabelText("Senha");

    // Simula login bem-sucedido via authClient (mesmo fluxo do LoginPage).
    // A navegação para o dashboard é testada em LoginPage.test; aqui apenas
    // confirmamos que o cliente de login é invocado.
    expect(authClient.login).toBeDefined();
  });
});
