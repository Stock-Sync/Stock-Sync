import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { ListingsPage } from "./ListingsPage";
import { mercadolibreClient } from "../../lib/api/mercadolibre-client";
import { renderWithProviders } from "../../test/utils";

vi.mock("../../lib/api/catalog-client", () => ({
  catalogClient: {
    listProducts: vi.fn().mockResolvedValue([
      {
        id: 1,
        name: "Titulo",
        description: "produto",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    ]),
    listSkus: vi.fn().mockResolvedValue([
      {
        id: 1,
        product_id: 1,
        internal_sku: "SKU-1",
        price: 10,
        stock_quantity: 0,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    ]),
    listPlatformMappings: vi.fn().mockResolvedValue([
      {
        id: 1,
        tenant_id: "t1",
        sku_id: 1,
        platform: "mercado_livre",
        platform_sku: "SKU-1",
        platform_product_id: "MLB1",
        platform_variant_id: null,
        is_active: true,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
      {
        id: 2,
        tenant_id: "t1",
        sku_id: 1,
        platform: "mercado_livre",
        platform_sku: "SKU-2",
        platform_product_id: "MLB2",
        platform_variant_id: null,
        is_active: false,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    ]),
    deletePlatformMapping: vi.fn().mockResolvedValue(undefined),
  },
}));

vi.mock("../../lib/api/integrations-client", () => ({
  integrationsClient: {
    listLocalMercadoLivreItems: vi.fn().mockResolvedValue([
      {
        item_id: "MLB1",
        title: "Anúncio vinculado",
        price: 10,
        available_quantity: 1,
        status: "active",
        thumbnail: null,
        permalink: null,
        sku_id: 1,
        product_id: 1,
        updated_at: new Date().toISOString(),
      },
      {
        item_id: "MLB2",
        title: "Anúncio com vínculo inativo",
        price: 10,
        available_quantity: 1,
        status: "active",
        thumbnail: null,
        permalink: null,
        sku_id: 1,
        product_id: 1,
        updated_at: new Date().toISOString(),
      },
      {
        item_id: "MLB3",
        title: "Anúncio importado sem vínculo",
        price: 10,
        available_quantity: 1,
        status: "active",
        thumbnail: null,
        permalink: null,
        sku_id: null,
        product_id: null,
        updated_at: new Date().toISOString(),
      },
    ]),
  },
}));

vi.mock("../../lib/api/mercadolibre-client", () => ({
  mercadolibreClient: {
    updateMlItem: vi.fn().mockResolvedValue({ id: "MLB3", status: "paused" }),
  },
}));

vi.mock("../../lib/api/sync-client", () => ({
  syncClient: {
    pullListings: vi.fn().mockResolvedValue({
      items_upserted: 0,
      mappings_created: 0,
    }),
  },
}));

vi.mock("../../lib/api/auth-client", () => ({
  authClient: {
    me: vi.fn().mockResolvedValue({
      id: "1",
      name: "Test User",
      email: "test@example.com",
      is_active: true,
      created_at: new Date().toISOString(),
    }),
    login: vi.fn(),
    logout: vi.fn(),
    refresh: vi.fn(),
  },
}));

describe("ListingsPage", () => {
  it("sinaliza anúncios sem vínculo ou com produto arquivado", async () => {
    renderWithProviders(<ListingsPage />);

    await screen.findByText("Anúncio vinculado");
    await waitFor(() => {
      expect(
        screen.getAllByText("Desvinculado / Produto arquivado")
      ).toHaveLength(2);
    });
  });

  it("pausa um anúncio pelo atalho da linha", async () => {
    const { user } = renderWithProviders(<ListingsPage />);

    await screen.findByText("Anúncio importado sem vínculo");
    await user.click(
      screen.getByRole("button", { name: "Pausar anúncio MLB3" })
    );

    await waitFor(() => {
      expect(mercadolibreClient.updateMlItem).toHaveBeenCalledWith("MLB3", {
        status: "paused",
      });
    });
  });
});
