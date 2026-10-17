import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { ListingWizardPage } from "./ListingWizardPage";
import { renderWithProviders } from "../../test/utils";
import { paths } from "../../routes/paths";

// Mock do catálogo interno (usado pelo combobox do passo 1).
vi.mock("../../lib/api/catalog-client", () => ({
  catalogClient: {
    listProducts: vi.fn().mockResolvedValue([
      {
        id: 1,
        name: "Camisa Algodão",
        description: "Camisa básica de algodão",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    ]),
    listSkus: vi.fn().mockResolvedValue([
      {
        id: 1,
        product_id: 1,
        internal_sku: "CAM-001",
        price: 49.9,
        stock_quantity: 10,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    ]),
  },
}));

// Mock do Mercado Livre (usado nos passos de categoria e publicação).
vi.mock("../../lib/api/mercadolibre-client", () => ({
  mercadolibreClient: {
    listSiteCategories: vi.fn().mockResolvedValue([
      { id: "MLB1055", name: "Eletrônicos, Áudio e Vídeo" },
      { id: "MLB1051", name: "Celulares e Telefones" },
    ]),
    getCategory: vi.fn().mockImplementation(async (categoryId: string) => {
      if (categoryId === "MLB1055") {
        return {
          id: "MLB1055",
          name: "Eletrônicos, Áudio e Vídeo",
          children_categories: [
            { id: "MLB11732", name: "TVs e Vídeo" },
            { id: "MLB1000", name: "Áudio" },
          ],
        };
      }
      // TVs e Vídeo é uma folha (sem filhos)
      return {
        id: "MLB11732",
        name: "TVs e Vídeo",
        children_categories: [],
      };
    }),
    getCategoryAttributes: vi.fn().mockResolvedValue([]),
  },
}));

// Mock do auth client (a rota de criação de anúncio exige sessão).
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
  },
}));

describe("ListingWizardPage", () => {
  it("avança para a categoria ao selecionar um produto do catálogo", async () => {
    const { user } = renderWithProviders(<ListingWizardPage />, {
      route: paths.listingNew,
    });

    await screen.findByText("Passo 1 de 5 — Seleção do produto base");

    await user.click(screen.getByLabelText("Produto base"));
    await waitFor(() => {
      expect(
        screen.getByRole("option", { name: /Camisa/ })
      ).toBeInTheDocument();
    });
    await user.click(screen.getByRole("option", { name: /Camisa/ }));

    await waitFor(() => {
      expect(
        screen.getByText("Passo 2 de 5 — Categoria do anúncio")
      ).toBeInTheDocument();
    });
    expect(screen.getByText("Camisa Algodão")).toBeInTheDocument();
    expect(screen.getByText("CAM-001")).toBeInTheDocument();
  });

  it("seleciona categoria via árvore e avança para os dados do anúncio", async () => {
    const { user } = renderWithProviders(<ListingWizardPage />, {
      route: paths.listingNew,
    });

    await screen.findByText("Passo 1 de 5 — Seleção do produto base");
    await user.click(screen.getByLabelText("Produto base"));
    await waitFor(() => {
      expect(
        screen.getByRole("option", { name: /Camisa/ })
      ).toBeInTheDocument();
    });
    await user.click(screen.getByRole("option", { name: /Camisa/ }));
    await waitFor(() => {
      expect(
        screen.getByText("Passo 2 de 5 — Categoria do anúncio")
      ).toBeInTheDocument();
    });

    // Clica para abrir a árvore de categorias
    await user.click(
      screen.getByRole("button", { name: /Navegar pela árvore de categorias/ })
    );

    // Clica na categoria "Eletrônicos, Áudio e Vídeo" para navegar (drill down)
    await user.click(
      screen.getByRole("button", { name: /Eletrônicos, Áudio e Vídeo/ })
    );

    // Agora mostra as subcategorias. Clica em "TVs e Vídeo" (que é uma folha)
    await user.click(
      screen.getByRole("button", { name: /TVs e Vídeo/ })
    );

    // Como "TVs e Vídeo" é uma folha, aparece o botão "Selecionar"
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /TVs e Vídeo.*Selecionar/ })
      ).toBeInTheDocument();
    });
    await user.click(
      screen.getByRole("button", { name: /TVs e Vídeo.*Selecionar/ })
    );

    await waitFor(() => {
      expect(
        screen.getByText("Passo 3 de 5 — Dados do anúncio")
      ).toBeInTheDocument();
    });
  });

  it("exige ao menos uma foto no passo de dados do anúncio", async () => {
    const { user } = renderWithProviders(<ListingWizardPage />, {
      route: paths.listingNew,
    });

    await screen.findByText("Passo 1 de 5 — Seleção do produto base");
    await user.click(screen.getByLabelText("Produto base"));
    await waitFor(() => {
      expect(
        screen.getByRole("option", { name: /Camisa/ })
      ).toBeInTheDocument();
    });
    await user.click(screen.getByRole("option", { name: /Camisa/ }));

    await waitFor(() => {
      expect(
        screen.getByText("Passo 2 de 5 — Categoria do anúncio")
      ).toBeInTheDocument();
    });

    // Abre árvore e seleciona categoria
    await user.click(
      screen.getByRole("button", { name: /Navegar pela árvore de categorias/ })
    );
    await user.click(
      screen.getByRole("button", { name: /Eletrônicos, Áudio e Vídeo/ })
    );
    await user.click(
      screen.getByRole("button", { name: /TVs e Vídeo/ })
    );
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /TVs e Vídeo.*Selecionar/ })
      ).toBeInTheDocument();
    });
    await user.click(
      screen.getByRole("button", { name: /TVs e Vídeo.*Selecionar/ })
    );
    await waitFor(() => {
      expect(
        screen.getByText("Passo 3 de 5 — Dados do anúncio")
      ).toBeInTheDocument();
    });

    await user.click(
      screen.getByRole("button", { name: /Próximo: atributos técnicos/ })
    );
    await waitFor(() => {
      expect(
        screen.getByText("Adicione pelo menos uma foto ao anúncio.")
      ).toBeInTheDocument();
    });
  });
});
