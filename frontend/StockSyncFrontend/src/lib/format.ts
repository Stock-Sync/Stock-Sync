const currencyFormatter = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
});

const dateTimeFormatter = new Intl.DateTimeFormat("pt-BR", {
  dateStyle: "medium",
  timeStyle: "short",
});

/** Formata valor monetário. Ex.: 10 -> "R$ 10,00". */
export function formatCurrency(value: number | null | undefined): string {
  return currencyFormatter.format(value ?? 0);
}

/**
 * Formata data/hora no padrão brasileiro.
 * Ex.: "2026-09-19T13:02:00Z" -> "19 de set. de 2026, 13:02".
 */
export function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "-";
  }
  return dateTimeFormatter.format(date);
}

/** Formata apenas a data. Ex.: "19 de set. de 2026". */
export function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "-";
  }
  return new Intl.DateTimeFormat("pt-BR", { dateStyle: "medium" }).format(
    date
  );
}

/** Primeira letra em maiúscula — usada nos avatares. */
export function initials(value: string): string {
  const trimmed = value.trim();
  if (trimmed.length === 0) {
    return "?";
  }
  return trimmed.charAt(0).toUpperCase();
}

/** Converte "10,50" ou "10.50" em número. Retorna NaN se inválido. */
export function parseDecimal(value: string): number {
  return Number(value.replace(",", "."));
}