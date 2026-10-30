/**
 * Envelope de erro do backend.
 *
 * Todos os serviços registram falhas com a mesma estrutura em
 * `app/api/handlers.py`. Mantemos o formato aqui para que o mock e o client
 * HTTP real falhem de maneira idêntica para a UI.
 */
export interface ApiErrorBody {
  ok: false;
  error: {
    code: string;
    message: string;
    details?: unknown;
  };
}

export class ApiError extends Error {
  code: string;
  details?: unknown;
  /** HTTP status when the error came from a real response. */
  status?: number;

  constructor(code: string, message: string, details?: unknown, status?: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.details = details;
    this.status = status;
  }
}

export const ERROR_CODES = {
  notFound: "not_found",
  conflict: "conflict",
  validationError: "validation_error",
  internalError: "internal_error",
} as const;