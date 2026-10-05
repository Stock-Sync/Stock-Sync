import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Card, CardBody, CardFooter } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { Input } from "../../components/ui/Input";
import { Select } from "../../components/ui/Select";
import { PageHeader } from "../../components/ui/PageHeader";
import { useToast } from "../../components/ui/toast-context";
import { useAuth } from "../../auth/auth-context";
import { PLATFORM_LABELS } from "../../types/catalog";
import { ApiError } from "../../types/api";
import { paths } from "../../routes/paths";
import { EMPTY_STORE_FORM } from "../../types/view-models";
import type { StoreFormValues } from "../../types/view-models";
import { useCreateStore, useStores } from "./queries";

type FormErrors = Partial<Record<keyof StoreFormValues, string>>;

// `Store.marketplace` guarda o rótulo exibido ("Shopee"), então o valor do
// select é o próprio rótulo.
const marketplaceOptions = Object.values(PLATFORM_LABELS).map((label) => ({
  value: label,
  label,
}));

/**
 * Formulário "Criar Loja" (Imagens 9 e 10).
 *
 * O campo Owner é um select com os usuários disponíveis — hoje apenas o usuário
 * da sessão, já que não existe modelo de usuário no backend.
 */
export function StoreFormPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { notify } = useToast();
  const createStore = useCreateStore();
  const { data: existingStores = [] } = useStores();

  const [values, setValues] = useState<StoreFormValues>(() => ({
    ...EMPTY_STORE_FORM,
    ownerId: user ? String(user.id) : "",
  }));
  const [errors, setErrors] = useState<FormErrors>({});

  const setField =
    (field: keyof StoreFormValues) =>
    (event: { target: { value: string } }) => {
      setValues((current) => ({ ...current, [field]: event.target.value }));
      setErrors((current) => ({ ...current, [field]: undefined }));
    };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const found: FormErrors = {};
    if (values.name.trim().length === 0) {
      found.name = "Informe o nome da loja.";
    }
    if (values.marketplace.trim().length === 0) {
      found.marketplace = "Selecione o marketplace.";
    }
    if (values.externalId.trim().length === 0) {
      found.externalId = "Informe o ID da loja no marketplace.";
    }
    if (values.ownerId.trim().length === 0) {
      found.ownerId = "Selecione o responsável.";
    }

    if (Object.keys(found).length > 0) {
      setErrors(found);
      return;
    }

    try {
      await createStore.mutateAsync({
        name: values.name.trim(),
        marketplace: values.marketplace,
        external_id: values.externalId.trim(),
        owner_id: Number(values.ownerId),
      });
      notify({ tone: "success", title: "Loja criada", description: values.name });
      navigate(paths.profile);
    } catch (caught) {
      notify({
        tone: "error",
        title: "Não foi possível criar a loja",
        description: caught instanceof ApiError ? caught.message : undefined,
      });
    }
  };

  // Evita oferecer a mesma loja duas vezes para o mesmo marketplace.
  const isDuplicate = existingStores.some(
    (store) =>
      store.name.trim().toLowerCase() === values.name.trim().toLowerCase() &&
      store.external_id.trim().toLowerCase() ===
        values.externalId.trim().toLowerCase()
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Criar Loja"
        description="Vincule uma conta de marketplace para publicar seus produtos."
      />

      <Card className="mx-auto w-full max-w-2xl">
        <form onSubmit={handleSubmit} noValidate>
          <CardBody className="space-y-5 p-6">
            <Input
              label="Name"
              value={values.name}
              onChange={setField("name")}
              error={errors.name}
            />
            <Select
              label="Marketplace"
              options={marketplaceOptions}
              placeholder="Selecione..."
              value={values.marketplace}
              onChange={setField("marketplace")}
              error={errors.marketplace}
            />
            <Input
              label="External id"
              value={values.externalId}
              onChange={setField("externalId")}
              error={errors.externalId}
              placeholder="ID da loja no marketplace"
            />
            <Select
              label="Owner"
              options={
                user
                  ? [{ value: String(user.id), label: user.username }]
                  : []
              }
              placeholder="Selecione..."
              value={values.ownerId}
              onChange={setField("ownerId")}
              error={errors.ownerId}
            />

            {isDuplicate && (
              <p className="rounded-xl bg-amber-50 px-3 py-2 text-sm font-medium text-amber-700">
                Já existe uma loja com o mesmo nome e External ID.
              </p>
            )}
          </CardBody>

          <CardFooter>
            <Button
              variant="secondary"
              onClick={() => navigate(-1)}
              disabled={createStore.isPending}
            >
              Cancelar
            </Button>
            <Button type="submit" disabled={createStore.isPending}>
              {createStore.isPending ? "Criando..." : "Criar"}
            </Button>
          </CardFooter>
        </form>
      </Card>
    </div>
  );
}