import { beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import { ProductsListPage } from "./ProductsListPage";
import { renderWithProviders } from "../../test/utils";
import { clearPersisted } from "../../mock/handlers";
import { db, resetDatabase } from "../../mock/db";

beforeEach(() => {
  resetDatabase();
  clearPersisted();
});

/** O seed do mock já contém o produto "rafael" / "Titulo" a R$ 10,00. */
describe("ProductsListPage", () => {
  it("mostra o produto semeado na tabela", async () => {
    renderWithProviders(<ProductsListPage />);

    expect(await screen.findByText("rafael")).toBeInTheDocument();
    expect(screen.getByText("Titulo")).toBeInTheDocument();
    expect(screen.getByText("R$ 10,00")).toBeInTheDocument();
  });

  it("filtra por SKU apenas após clicar em Buscar", async () => {
    const { user } = renderWithProviders(<ProductsListPage />);

    await screen.findByText("Titulo");

    // Registra um segundo produto para que o filtro tenha o que excluir.
    db.products.push({
      id: 2,
      name: "Outro",
      description: null,
      created_at: "2026-01-01T00:00:00.000Z",
      updated_at: "2026-01-01T00:00:00.000Z",
    });
    db.skus.push({
      id: 2,
      product_id: 2,
      internal_sku: "sku-2",
      price: 99,
      stock_quantity: 0,
      created_at: "2026-01-01T00:00:00.000Z",
      updated_at: "2026-01-01T00:00:00.000Z",
    });

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

  it("pede confirmação antes de apagar", async () => {
    const { user } = renderWithProviders(<ProductsListPage />);

    await screen.findByText("Titulo");
    await user.click(screen.getByRole("button", { name: "Apagar Titulo" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Apagar produto")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "Apagar" }));

    await waitFor(() => {
      expect(db.products).toHaveLength(0);
      expect(db.skus).toHaveLength(0);
    });
  });
});