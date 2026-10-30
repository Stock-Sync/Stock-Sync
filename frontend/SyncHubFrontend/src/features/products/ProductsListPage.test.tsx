import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import { ProductsListPage } from "./ProductsListPage";
import { mercadolibreClient } from "../../lib/api/mercadolibre-client";
import { renderWithProviders } from "../../test/utils";

vi.mock("../../lib/api/mercadolibre-client", () => ({
  mercadolibreClient: {
    updateMlItem: vi.fn().mockResolvedValue({ id: "MLB1", status: "paused" }),
  },
}));

// Mock the catalog client for tests.
// O catálogo é stateful: o deleteProduct remove o produto da lista devolvida
// pelo listProducts, para que o refetch pós-invalidação reflita a remoção.
const seededProducts = [
  { id: 1, name: "Titulo", description: "produto rafa", created_at: "2026-09-19T13:02:00.000Z", updated_at: "2026-09-19T13:02:00.000Z" },
];
const deletedProductIds = new Set<number>();

vi.mock("../../lib/api/catalog-client", () => ({
  catalogClient: {
    listProducts: vi.fn().mockImplementation(async () =>
      seededProducts.filter((product) => !deletedProductIds.has(product.id))
    ),
    listSkus: vi.fn().mockImplementation(async () =>
      [
        { id: 1, product_id: 1, internal_sku: "rafael", price: 10, stock_quantity: 0, created_at: "2026-09-19T13:02:00.000Z", updated_at: "2026-09-19T13:02:00.000Z" },
      ].filter((sku) => !deletedProductIds.has(sku.product_id))
    ),
    createProduct: vi.fn().mockResolvedValue({ id: 2, name: "Outro", description: null, created_at: new Date().toISOString(), updated_at: new Date().toISOString() }),
    createSku: vi.fn().mockResolvedValue({ id: 2, product_id: 2, internal_sku: "sku-2", price: 99, stock_quantity: 0, created_at: new Date().toISOString(), updated_at: new Date().toISOString() }),
    updateProduct: vi.fn().mockResolvedValue({ id: 1, name: "Titulo", description: "produto rafa", created_at: new Date().toISOString(), updated_at: new Date().toISOString() }),
    updateSku: vi.fn().mockResolvedValue({ id: 1, product_id: 1, internal_sku: "rafael", price: 10, stock_quantity: 0, created_at: new Date().toISOString(), updated_at: new Date().toISOString() }),
    deleteProduct: vi.fn().mockImplementation(async (id: number) => {
      deletedProductIds.add(id);
    }),
    deleteSku: vi.fn().mockResolvedValue(undefined),
    listPlatformMappings: vi.fn().mockResolvedValue([
      {
        id: 1,
        tenant_id: "test-tenant",
        sku_id: 1,
        platform: "mercado_livre",
        platform_sku: "ML-1",
        platform_product_id: "MLB1",
        platform_variant_id: null,
        is_active: true,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    ]),
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

describe("ProductsListPage", () => {
  beforeEach(() => {
    deletedProductIds.clear();
  });

  it("mostra o produto semeado na tabela", async () => {
    renderWithProviders(<ProductsListPage />);

    expect(await screen.findByText("rafael")).toBeInTheDocument();
    expect(screen.getByText("Titulo")).toBeInTheDocument();
    expect(screen.getByText("R$ 10,00")).toBeInTheDocument();
  });

  it("filtra por SKU apenas após clicar em Buscar", async () => {
    const { user } = renderWithProviders(<ProductsListPage />);

    await screen.findByText("Titulo");

    await user.type(
      screen.getByLabelText("Buscar SKU ou titulo"),
      "rafael"
    );
    await user.click(screen.getByRole("button", { name: "Buscar" }));

    await waitFor(() => {
      expect(screen.queryByText("Outro")).not.toBeInTheDocument();
    });
    expect(screen.getByText("Titulo")).toBeInTheDocument();
  });

  it("alterna para a visualização em grade", async () => {
    const { user } = renderWithProviders(<ProductsListPage />);

    await screen.findByText("Titulo");
    await user.click(screen.getByRole("button", { name: "Ver como grade" }));

    const gridButton = screen.getByRole("button", { name: "Ver como grade" });
    expect(gridButton).toHaveAttribute("aria-pressed", "true");

    // A tabela some e os cards aparecem.
    expect(
      screen.queryByRole("table", { name: /lista de produtos/i })
    ).not.toBeInTheDocument();
  });

  it("aborta a exclusão quando a pausa do anúncio falha", async () => {
    const { user } = renderWithProviders(<ProductsListPage />);

    await screen.findByText("Titulo");
    await user.click(screen.getByRole("button", { name: "Apagar Titulo" }));

    const dialog = await screen.findByRole("dialog");
    await within(dialog).findByText(/Mercado Livre \(ML-1\)/);
    vi.mocked(mercadolibreClient.updateMlItem).mockRejectedValueOnce(
      new Error("ML unavailable")
    );

    await user.click(within(dialog).getByRole("button", { name: "Apagar" }));

    await waitFor(() => {
      expect(screen.getByText("Titulo")).toBeInTheDocument();
    });
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("pede confirmação antes de apagar", async () => {
    const { user } = renderWithProviders(<ProductsListPage />);

    await screen.findByText("Titulo");
    await user.click(screen.getByRole("button", { name: "Apagar Titulo" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Apagar produto")).toBeInTheDocument();
    expect(
      await within(dialog).findByText(/Mercado Livre \(ML-1\)/)
    ).toBeInTheDocument();
    expect(
      within(dialog).getByRole("checkbox", {
        name: /Pausar\/Encerrar os anúncios no Mercado Livre/i,
      })
    ).toBeChecked();

    await user.click(within(dialog).getByRole("button", { name: "Apagar" }));

    await waitFor(() => {
      // Product deleted successfully
      expect(screen.queryByText("Titulo")).not.toBeInTheDocument();
    });
    expect(mercadolibreClient.updateMlItem).toHaveBeenCalledWith("MLB1", {
      status: "paused",
    });
  });
});