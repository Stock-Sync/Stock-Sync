import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Card, CardBody } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { Input } from "../../components/ui/Input";
import { useAuth } from "../../auth/auth-context";
import { paths } from "../../routes/paths";
import { ApiError } from "../../types/api";

interface RedirectState {
  from?: { pathname?: string };
  registered?: boolean;
}

/**
 * Tela de login (Imagem 2).
 *
 * Após autenticar, retorna o usuário à rota que originou o redirect. É o que
 * faz "Criar Produto" deslogado abrir o formulário preenchido pós-login.
 */
export function LoginPage() {
  const { login, isLoading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Mostra mensagem de sucesso após registro
  const registered = (location.state as RedirectState | null)?.registered;

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      await login(email, password);
      const state = location.state as RedirectState | null;
      navigate(state?.from?.pathname ?? paths.dashboard, { replace: true });
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Não foi possível entrar. Tente novamente."
      );
      setIsSubmitting(false);
    }
  };

  // Mostra loading enquanto verifica autenticação inicial
  if (isLoading) {
    return (
      <div className="flex justify-center py-10">
        <div className="flex items-center gap-2 text-slate-500">
          <div className="animate-spin rounded-full h-5 w-5 border-2 border-brand-500 border-t-transparent" />
          <span>Verificando sessão...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-center py-10">
      <Card className="w-full max-w-sm">
        <CardBody className="space-y-5 p-6">
          <div>
            <h1 className="text-xl font-bold text-slate-900">Entrar</h1>
            <p className="mt-1 text-sm text-slate-500">
              Acesse sua conta para gerenciar o catálogo.
            </p>
          </div>

          {registered && (
            <p
              role="status"
              className="rounded-xl bg-green-50 px-3 py-2 text-sm font-medium text-green-700"
            >
              Conta criada com sucesso! Faça login para continuar.
            </p>
          )}

          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
            <Input
              label="E-mail"
              name="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="seu@email.com"
            />
            <Input
              label="Senha"
              name="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />

            {error && (
              <p
                role="alert"
                className="rounded-xl bg-red-50 px-3 py-2 text-sm font-medium text-red-700"
              >
                {error}
              </p>
            )}

            <Button
              type="submit"
              fullWidth
              disabled={isSubmitting}
              className="rounded-full"
            >
              {isSubmitting ? "Entrando..." : "Entrar"}
            </Button>
          </form>

          <p className="text-center text-sm text-slate-500">
            Não tem conta?{" "}
            <Link
              to={paths.register}
              className="font-medium text-brand-700 hover:underline"
            >
              Criar conta
            </Link>
          </p>

          <Link
            to={paths.dashboard}
            className="block text-center text-sm font-medium text-brand-700 hover:underline"
          >
            Voltar ao início
          </Link>
        </CardBody>
      </Card>
    </div>
  );
}