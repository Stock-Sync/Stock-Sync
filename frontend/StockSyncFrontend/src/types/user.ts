/**
 * Usuário autenticado.
 *
 * Não existe modelo de usuário no backend ainda — a sessão é mockada e
 * persistida em localStorage. Quando o auth real entrar, troque o provider
 * por uma chamada de login que devolva um `User` com o mesmo formato.
 */
export interface User {
  id: number;
  username: string;
  email: string;
}