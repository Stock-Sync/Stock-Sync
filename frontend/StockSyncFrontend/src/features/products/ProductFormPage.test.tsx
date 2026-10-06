import { beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { ProductFormPage } from "./ProductFormPage";
import { renderAtRoute, renderWithProviders } from "../../test/utils";
import { clearPersisted, hydrate } from "../../mock/handlers";
import { db, resetDatabase } from "../../mock/db";

/** A criação de produto depende do `db` global do mock. */
beforeEach(() => {
  resetDatabase();
  clearPersisted();
});

describe("ProductFormPage — criação", () => {
  it("exibe os campos do formulário da Imagem 3", () => {
    renderWithProviders(<ProductFormPage mode="create" />);

    expect(screen.getByLabelText("Sku")).toBeInTheDocument();
    expect(screen.getByLabelText("Title")).toBeInTheDocument();
    expect(screen.getByLabelText("Description")).toBeInTheDocument();
    expect(screen.getByLabelText("Price")).toBeInTheDocument();
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

    await user.type(screen.getByLabelText("Sku"), "abc");
    await user.type(screen.getByLabelText("Title"), "Produto teste");
    await user.type(screen.getByLabelText("Price"), "-5");
    await user.click(screen.getByRole("button", { name: "Criar" }));

    expect(
      await screen.findByText("O preço não pode ser negativo.")
    ).toBeInTheDocument();
  });

  it("cria o produto e o SKU correspondente", async () => {
    const { user } = renderWithProviders(<ProductFormPage mode="create" />);

    await user.type(screen.getByLabelText("Sku"), "rafael");
    await user.type(screen.getByLabelText("Title"), "Titulo");
    await user.type(screen.getByLabelText("Description"), "produto rafa");
    await user.type(screen.getByLabelText("Price"), "10");
    await user.click(screen.getByRole("button", { name: "Criar" }));

    await waitFor(() => {
      expect(db.products.some((p) => p.name === "Titulo")).toBe(true);
    });

    const sku = db.skus.find((item) => item.internal_sku === "rafael");
    expect(sku).toBeDefined();
    expect(sku?.price).toBe(10);
  });

  it("bloqueia SKU duplicado com a mensagem de conflito", async () => {
    const { user } = renderWithProviders(<ProductFormPage mode="create" />);

    // O seed já contém o SKU "rafael".
    await user.type(screen.getByLabelText("Sku"), "rafael");
    await user.type(screen.getByLabelText("Title"), "Outro produto");
    await user.type(screen.getByLabelText("Price"), "20");
    await user.click(screen.getByRole("button", { name: "Criar" }));

    expect(
      await screen.findByText(/Já existe um produto com o SKU "rafael"/)
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
      expect(screen.getByLabelText("Sku")).toHaveValue("rafael");
    });
    expect(screen.getByLabelText("Title")).toHaveValue("Titulo");
    expect(screen.getByLabelText("Description")).toHaveValue("produto rafa");
    expect(screen.getByLabelText("Price")).toHaveValue("10");
  });

  it("salva as alterações no produto e no SKU", async () => {
    const { user } = renderAtRoute(<ProductFormPage mode="edit" />, {
      path: "/products/:id/edit",
      route: "/products/1/edit",
    });

    await waitFor(() => {
      expect(screen.getByLabelText("Title")).toHaveValue("Titulo");
    });

    const title = screen.getByLabelText("Title");
    await user.clear(title);
    await user.type(title, "Titulo atualizado");
    await user.click(screen.getByRole("button", { name: "Salvar" }));

    await waitFor(() => {
      expect(db.products[0]?.name).toBe("Titulo atualizado");
    });
  });

  it("mostra estado vazio quando o produto não existe", async () => {
    renderAtRoute(<ProductFormPage mode="edit" />, {
      path: "/products/:id/edit",
      route: "/products/999/edit",
    });

    expect(
      await screen.findByText("Produto não encontrado")
    ).toBeInTheDocument();
  });
});

describe("persistência do mock", () => {
  it("hidrata o db a partir do localStorage", async () => {
    resetDatabase();
    db.products = [];
    db.skus = [];

    window.localStorage.setItem(
      "stocksync:products",
      JSON.stringify([
        {
          id: 7,
          name: "Do storage",
          description: null,
          created_at: "2026-01-01T00:00:00.000Z",
          updated_at: "2026-01-01T00:00:00.000Z",
        },
      ])
    );
    window.localStorage.setItem(
      "stocksync:skus",
      JSON.stringify([
        {
          id: 7,
          product_id: 7,
          internal_sku: "persistido",
          price: 42,
          stock_quantity: 3,
          created_at: "2026-01-01T00:00:00.000Z",
          updated_at: "2026-01-01T00:00:00.000Z",
        },
      ])
    );

    hydrate();

    expect(db.products).toHaveLength(1);
    expect(db.products[0]?.name).toBe("Do storage");
    expect(db.skus[0]?.internal_sku).toBe("persistido");
  });
});