import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import { ProductsListPage } from "./ProductsListPage";
import { mercadolibreClient } from "../../lib/api/mercadolibre-client";
import { renderWithProviders } from "../../test/utils";
import { ApiError } from "../../types/api";

const state = vi.hoisted(() => ({
  deletedProductIds: new Set<number>(),
  unboundProductIds: new Set<number>(),
  activeListings: null as Array<{
    id: string;
    status: string | null;
    permalink: string | null;
  }> | null,
  updateCalls: [] as Array<[string, Record<string, unknown>]>,
  seededProducts: [
    {
      id: 1,
      name: "Titulo",
      description: "produto rafa",
      created_at: "2026-09-19T13:02:00.000Z",
      updated_at: "2026-09-19T13:02:00.000Z",
    },
  ],
}));

// O ML é remoto: pausar/zerar um anúncio ativo faz o backend liberar a
// exclusão (o mapping local passa a inativo).
vi.mock("../../lib/api/mercadolibre-client", () => ({
  mercadolibreClient: {
    updateMlItem: vi
      .fn()
      .mockImplementation(
        async (id: string, payload: Record<string, unknown>) => {
          state.updateCalls.push([id, payload]);
          state.activeListings = null;
          return { id, status: payload.status ?? "paused" };
        }
      ),
  },
}));

// Mock the catalog client for tests.
// O catálogo é stateful: o deleteProduct remove o produto da lista devolvida
// pelo listProducts, para que o refetch pós-invalidação reflita a remoção.
vi.mock("../../lib/api/catalog-client", () => ({
  catalogClient: {
    listProducts: vi
      .fn()
      .mockImplementation(async () =>
        state.seededProducts.filter(
          (product) => !state.deletedProductIds.has(product.id)
        )
      ),
    listSkus: vi.fn().mockImplementation(async () =>
      [
        {
          id: 1,
          product_id: 1,
          internal_sku: "rafael",
          price: 10,
          stock_quantity: 0,
          created_at: "2026-09-19T13:02:00.000Z",
          updated_at: "2026-09-19T13:02:00.000Z",
        },
      ].filter((sku) => !state.deletedProductIds.has(sku.product_id))
    ),
    createProduct: vi.fn().mockResolvedValue({
      id: 2,
      name: "Outro",
      description: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }),
    createSku: vi.fn().mockResolvedValue({
      id: 2,
      product_id: 2,
      internal_sku: "sku-2",
      price: 99,
      stock_quantity: 0,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }),
    updateProduct: vi.fn().mockResolvedValue({
      id: 1,
      name: "Titulo",
      description: "produto rafa",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }),
    updateSku: vi.fn().mockResolvedValue({
      id: 1,
      product_id: 1,
      internal_sku: "rafael",
      price: 10,
      stock_quantity: 0,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }),
    deleteProduct: vi.fn().mockImplementation(async (id: number) => {
      // Plan 10: active listings block the deletion with a structured 409
      // until they are paused or unlinked.
      if (state.activeListings && !state.unboundProductIds.has(id)) {
        throw new ApiError(
          "product_has_active_listings",
          "Não é possível excluir um produto com anúncios ativos vinculados.",
          {
            product_id: id,
            product_name: "Titulo",
            listings: state.activeListings,
          },
          409
        );
      }
      state.deletedProductIds.add(id);
    }),
    unbindProductListings: vi.fn().mockImplementation(async (id: number) => {
      state.unboundProductIds.add(id);
      return { unbound: 1, platform_product_ids: ["MLB1"] };
    }),
    deleteSku: vi.fn().mockResolvedValue(undefined),
    listPlatformMappings: vi.fn().mockResolvedValue([]),
    listMappings: vi.fn().mockResolvedValue([]),
    createMappingForSku: vi.fn().mockResolvedValue({
      id: 1,
      sku_id: 1,
      platform: "mercadolivre",
      platform_sku: "ML-1",
      platform_product_id: "1",
      platform_variant_id: "1",
      is_active: true,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }),
    deleteMapping: vi.fn().mockResolvedValue(undefined),
  },
}));

// Mock the auth client
vi.mock("../../lib/api/auth-client", () => ({
  authClient: {
    me: vi.fn().mockResolvedValue({
      id: "1",
      name: "Test User",
      email: "test@example.com",
      is_active: true,
      created_at: new Date().toISOString(),
    }),
    login: vi.fn().mockResolvedValue({
      user: {
        id: "1",
        name: "Test User",
        email: "test@example.com",
        is_active: true,
        created_at: new Date().toISOString(),
      },
    }),
    logout: vi.fn().mockResolvedValue({ message: "Logged out" }),
  },
}));

const CONFLICT_LISTING = {
  id: "MLB1",
  status: "active",
  permalink: "https://produto.mercadolivre.com.br/MLB-1",
};

describe("ProductsListPage", () => {
  beforeEach(() => {
    state.deletedProductIds.clear();
    state.unboundProductIds.clear();
    state.activeListings = null;
    state.updateCalls = [];
    vi.mocked(mercadolibreClient.updateMlItem).mockClear();
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

    await user.type(screen.getByLabelText("Buscar SKU ou titulo"), "rafael");
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

  it("pede confirmação antes de apagar", async () => {
    const { user } = renderWithProviders(<ProductsListPage />);

    await screen.findByText("Titulo");
    await user.click(screen.getByRole("button", { name: "Apagar Titulo" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Apagar produto")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "Apagar" }));

    await waitFor(() => {
      expect(screen.queryByText("Titulo")).not.toBeInTheDocument();
    });
  });

  it("mostra o diálogo de resolução quando há anúncios ativos", async () => {
    state.activeListings = [CONFLICT_LISTING];
    const { user } = renderWithProviders(<ProductsListPage />);

    await screen.findByText("Titulo");
    await user.click(screen.getByRole("button", { name: "Apagar Titulo" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", {
        name: "Apagar",
      })
    );

    const dialog = await screen.findByRole("dialog", {
      name: "Anúncios ativos vinculados",
    });
    expect(within(dialog).getByText(/MLB1/)).toBeInTheDocument();
    expect(within(dialog).getByText("Ativo")).toBeInTheDocument();
    expect(
      within(dialog).getByRole("button", { name: /Pausar e zerar/ })
    ).toBeInTheDocument();
    expect(
      within(dialog).getByRole("button", { name: /Desvincular/ })
    ).toBeInTheDocument();
    expect(
      within(dialog).getByRole("button", {
        name: /Pausar, zerar e desvincular/,
      })
    ).toBeInTheDocument();
    expect(
      within(dialog).getByRole("link", { name: /Abrir anúncio no ML/ })
    ).toHaveAttribute("href", CONFLICT_LISTING.permalink);
    expect(
      within(dialog).getByRole("button", { name: "Cancelar" })
    ).toBeInTheDocument();

    // Nada foi alterado ainda.
    expect(state.updateCalls).toEqual([]);
    expect(state.deletedProductIds.size).toBe(0);
    expect(screen.getByText("Titulo")).toBeInTheDocument();
  });

  it("pausar e zerar conclui a exclusão", async () => {
    state.activeListings = [CONFLICT_LISTING];
    const { user } = renderWithProviders(<ProductsListPage />);

    await screen.findByText("Titulo");
    await user.click(screen.getByRole("button", { name: "Apagar Titulo" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", {
        name: "Apagar",
      })
    );
    const dialog = await screen.findByRole("dialog", {
      name: "Anúncios ativos vinculados",
    });

    await user.click(
      within(dialog).getByRole("button", { name: /Pausar e zerar/ })
    );

    await waitFor(() => {
      expect(screen.queryByText("Titulo")).not.toBeInTheDocument();
    });
    expect(state.updateCalls).toEqual([
      ["MLB1", { status: "paused", available_quantity: 0 }],
    ]);
    expect(state.deletedProductIds.has(1)).toBe(true);
  });

  it("desvincular conclui a exclusão sem tocar no marketplace", async () => {
    state.activeListings = [CONFLICT_LISTING];
    const { user } = renderWithProviders(<ProductsListPage />);

    await screen.findByText("Titulo");
    await user.click(screen.getByRole("button", { name: "Apagar Titulo" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", {
        name: "Apagar",
      })
    );
    const dialog = await screen.findByRole("dialog", {
      name: "Anúncios ativos vinculados",
    });

    await user.click(
      within(dialog).getByRole("button", { name: /Desvincular/ })
    );

    await waitFor(() => {
      expect(screen.queryByText("Titulo")).not.toBeInTheDocument();
    });
    expect(state.unboundProductIds.has(1)).toBe(true);
    expect(state.updateCalls).toEqual([]);
    expect(state.deletedProductIds.has(1)).toBe(true);
  });

  it("pausar, zerar e desvincular executa as duas ações", async () => {
    state.activeListings = [CONFLICT_LISTING];
    const { user } = renderWithProviders(<ProductsListPage />);

    await screen.findByText("Titulo");
    await user.click(screen.getByRole("button", { name: "Apagar Titulo" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", {
        name: "Apagar",
      })
    );
    const dialog = await screen.findByRole("dialog", {
      name: "Anúncios ativos vinculados",
    });

    await user.click(
      within(dialog).getByRole("button", {
        name: /Pausar, zerar e desvincular/,
      })
    );

    await waitFor(() => {
      expect(screen.queryByText("Titulo")).not.toBeInTheDocument();
    });
    expect(state.updateCalls).toEqual([
      ["MLB1", { status: "paused", available_quantity: 0 }],
    ]);
    expect(state.unboundProductIds.has(1)).toBe(true);
    expect(state.deletedProductIds.has(1)).toBe(true);
  });

  it("aborta a exclusão quando a pausa do anúncio falha", async () => {
    state.activeListings = [CONFLICT_LISTING];
    const { user } = renderWithProviders(<ProductsListPage />);

    await screen.findByText("Titulo");
    await user.click(screen.getByRole("button", { name: "Apagar Titulo" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", {
        name: "Apagar",
      })
    );
    const dialog = await screen.findByRole("dialog", {
      name: "Anúncios ativos vinculados",
    });

    vi.mocked(mercadolibreClient.updateMlItem).mockRejectedValueOnce(
      new Error("ML unavailable")
    );
    await user.click(
      within(dialog).getByRole("button", { name: /Pausar e zerar/ })
    );

    await waitFor(() => {
      expect(screen.getByText("Titulo")).toBeInTheDocument();
    });
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(state.deletedProductIds.size).toBe(0);
  });

  it("cancelar mantém o produto e não altera o marketplace", async () => {
    state.activeListings = [CONFLICT_LISTING];
    const { user } = renderWithProviders(<ProductsListPage />);

    await screen.findByText("Titulo");
    await user.click(screen.getByRole("button", { name: "Apagar Titulo" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", {
        name: "Apagar",
      })
    );
    const dialog = await screen.findByRole("dialog", {
      name: "Anúncios ativos vinculados",
    });

    await user.click(within(dialog).getByRole("button", { name: "Cancelar" }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(screen.getByText("Titulo")).toBeInTheDocument();
    expect(state.updateCalls).toEqual([]);
    expect(state.deletedProductIds.size).toBe(0);
  });
});
