/**
 * Usuário autenticado.
 *
 * Corresponde ao modelo retornado pelo auth-service.
 * O id é UUID (string) vindo do backend.
 */
export interface User {
  id: string;
  username: string;
  email: string;
}