import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Card, CardBody } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { Input } from "../../components/ui/Input";
import { authClient } from "../../lib/api/auth-client";
import { paths } from "../../routes/paths";
import { ApiError } from "../../types/api";

/**
 * Tela de cadastro de usuário.
 *
 * Validações:
 * - Nome: obrigatório
 * - E-mail: formato válido
 * - Senha: mínimo 8 caracteres, pelo menos 1 número e 1 símbolo
 */
export function RegisterPage() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const validateForm = (): string | null => {
    if (!name.trim()) {
      return "Nome é obrigatório";
    }
    if (!email.trim()) {
      return "E-mail é obrigatório";
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      return "E-mail inválido";
    }
    if (password.length < 8) {
      return "A senha deve ter no mínimo 8 caracteres";
    }
    if (!/\d/.test(password)) {
      return "A senha deve conter pelo menos um número";
    }
    if (!/[!@#$%^&*()_+\-=[\]{};':"\\|,.<>/?]/.test(password)) {
      return "A senha deve conter pelo menos um símbolo (!@#$%^&*...)";
    }
    if (password !== confirmPassword) {
      return "As senhas não coincidem";
    }
    return null;
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);

    const validationError = validateForm();
    if (validationError) {
      setError(validationError);
      return;
    }

    setIsSubmitting(true);

    try {
      await authClient.register({ name: name.trim(), email: email.trim(), password });
      
      // Sucesso - redireciona para login com mensagem
      navigate(paths.login, { 
        replace: true, 
        state: { registered: true } 
      });
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Não foi possível criar a conta. Tente novamente."
      );
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex justify-center py-10">
      <Card className="w-full max-w-sm">
        <CardBody className="space-y-5 p-6">
          <div>
            <h1 className="text-xl font-bold text-slate-900">Criar conta</h1>
            <p className="mt-1 text-sm text-slate-500">
              Preencha os dados abaixo para começar.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
            <Input
              label="Nome"
              name="name"
              autoComplete="name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Seu nome completo"
            />
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
              autoComplete="new-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Mín. 8 chars, 1 número, 1 símbolo"
            />
            <Input
              label="Confirmar senha"
              name="confirmPassword"
              type="password"
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              placeholder="Repita a senha"
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
              {isSubmitting ? "Criando conta..." : "Criar conta"}
            </Button>
          </form>

          <p className="text-center text-sm text-slate-500">
            Já tem conta?{" "}
            <Link
              to={paths.login}
              className="font-medium text-brand-700 hover:underline"
            >
              Entrar
            </Link>
          </p>
        </CardBody>
      </Card>
    </div>
  );
}