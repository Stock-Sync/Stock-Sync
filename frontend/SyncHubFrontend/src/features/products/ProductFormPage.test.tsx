import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { ProductFormPage } from "./ProductFormPage";
import { renderAtRoute, renderWithProviders } from "../../test/utils";

// Mock the catalog client for tests
vi.mock("../../lib/api/catalog-client", () => ({
  catalogClient: {
    listProducts: vi.fn().mockResolvedValue([{ id: 1, name: "Titulo", description: "produto rafa", created_at: new Date().toISOString(), updated_at: new Date().toISOString() }]),
    listSkus: vi.fn().mockResolvedValue([{ id: 1, product_id: 1, internal_sku: "rafael", price: 10, stock_quantity: 0, created_at: new Date().toISOString(), updated_at: new Date().toISOString() }]),
    createProduct: vi.fn().mockResolvedValue({ id: 1, name: "Titulo", description: "produto rafa", created_at: new Date().toISOString(), updated_at: new Date().toISOString() }),
    createSku: vi.fn().mockResolvedValue({ id: 1, product_id: 1, internal_sku: "rafael", price: 10, stock_quantity: 0, created_at: new Date().toISOString(), updated_at: new Date().toISOString() }),
    updateProduct: vi.fn().mockResolvedValue({ id: 1, name: "Titulo atualizado", description: "produto rafa", created_at: new Date().toISOString(), updated_at: new Date().toISOString() }),
    updateSku: vi.fn().mockResolvedValue({ id: 1, product_id: 1, internal_sku: "rafael", price: 10, stock_quantity: 0, created_at: new Date().toISOString(), updated_at: new Date().toISOString() }),
    deleteProduct: vi.fn().mockResolvedValue(undefined),
    deleteSku: vi.fn().mockResolvedValue(undefined),
    listMappings: vi.fn().mockResolvedValue([]),
    createMappingForSku: vi.fn().mockResolvedValue({ id: 1, sku_id: 1, platform: "mercadolivre", platform_sku: "ML-1", platform_product_id: "1", platform_variant_id: "1", is_active: true, created_at: new Date().toISOString(), updated_at: new Date().toISOString() }),
    deleteMapping: vi.fn().mockResolvedValue(undefined),
  },
}));

// Mock the auth client
vi.mock("../../lib/api/auth-client", () => ({
  authClient: {
    me: vi.fn().mockResolvedValue({ id: "1", name: "Test User", email: "test@example.com", is_active: true, created_at: new Date().toISOString() }),
    login: vi.fn().mockResolvedValue({ user: { id: "1", name: "Test User", email: "test@example.com", is_active: true, created_at: new Date().toISOString() } }),
    logout: vi.fn().mockResolvedValue({ message: "Logged out" }),
  },
}));

describe("ProductFormPage — criação", () => {
  it("exibe os campos do formulário da Imagem 3", () => {
    renderWithProviders(<ProductFormPage mode="create" />);

    expect(screen.getByLabelText("SKU do Produto")).toBeInTheDocument();
    expect(screen.getByLabelText("Título do Produto")).toBeInTheDocument();
    expect(screen.getByLabelText("Descrição")).toBeInTheDocument();
    expect(screen.getByLabelText("Preço Base (R$)")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Criar" })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Cancelar" })
    ).toBeInTheDocument();
  });

  it("exige SKU, título e preço", async () => {
    const { user } = renderWithProviders(<ProductFormPage mode="create" />);

    await user.click(screen.getByRole("button", { name: "Criar" }));

    expect(await screen.findByText("Informe o SKU do produto.")).toBeInTheDocument();
    expect(screen.getByText("Informe o título do produto.")).toBeInTheDocument();
    expect(screen.getByText("Informe o preço do produto.")).toBeInTheDocument();
  });

  it("rejeita preço negativo", async () => {
    const { user } = renderWithProviders(<ProductFormPage mode="create" />);

    await user.type(screen.getByLabelText("SKU do Produto"), "abc");
    await user.type(screen.getByLabelText("Título do Produto"), "Produto teste");
    await user.type(screen.getByLabelText("Preço Base (R$)"), "-5");
    await user.click(screen.getByRole("button", { name: "Criar" }));

    expect(
      await screen.findByText("O preço não pode ser negativo.")
    ).toBeInTheDocument();
  });
});

describe("ProductFormPage — edição", () => {
  it("preenche os campos com os dados do produto", async () => {
    renderAtRoute(<ProductFormPage mode="edit" />, {
      path: "/products/:id/edit",
      route: "/products/1/edit",
    });

    await waitFor(() => {
      expect(screen.getByLabelText("SKU do Produto")).toHaveValue("rafael");
    });
    expect(screen.getByLabelText("Título do Produto")).toHaveValue("Titulo");
    expect(screen.getByLabelText("Descrição")).toHaveValue("produto rafa");
    expect(screen.getByLabelText("Preço Base (R$)")).toHaveValue("10");
  });
});