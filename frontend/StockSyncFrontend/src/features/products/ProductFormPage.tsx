import { useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Card, CardBody, CardFooter } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { Input } from "../../components/ui/Input";
import { Textarea } from "../../components/ui/Textarea";
import { PageHeader } from "../../components/ui/PageHeader";
import { LoadingBlock } from "../../components/ui/Spinner";
import { EmptyState } from "../../components/ui/EmptyState";
import { useToast } from "../../components/ui/toast-context";
import { parseDecimal } from "../../lib/format";
import { paths } from "../../routes/paths";
import { ApiError } from "../../types/api";
import { EMPTY_PRODUCT_FORM } from "../../types/view-models";
import type { ProductFormValues, ProductView } from "../../types/view-models";
import {
  useCreateProduct,
  useProductView,
  useUpdateProduct,
} from "./queries";

type FormErrors = Partial<Record<keyof ProductFormValues, string>>;

function validate(values: ProductFormValues): FormErrors {
  const errors: FormErrors = {};

  if (values.sku.trim().length === 0) {
    errors.sku = "Informe o SKU do produto.";
  }
  if (values.title.trim().length === 0) {
    errors.title = "Informe o título do produto.";
  }
  if (values.price.trim().length === 0) {
    errors.price = "Informe o preço do produto.";
  } else if (Number.isNaN(parseDecimal(values.price))) {
    errors.price = "Preço inválido. Use apenas números.";
  } else if (parseDecimal(values.price) < 0) {
    errors.price = "O preço não pode ser negativo.";
  }

  return errors;
}

/** Campos compartilhados por criação e edição. */
interface ProductFormFieldsProps {
  mode: "create" | "edit";
  initial: ProductFormValues;
  isSubmitting: boolean;
  /** Erros vindos da API, como SKU duplicado. */
  serverErrors?: FormErrors;
  onSubmit: (values: ProductFormValues) => Promise<void>;
  onCancel: () => void;
}

/**
 * Campos do formulário.
 *
 * Recebe os valores iniciais por prop e só os usa no `useState` inicial, então
 * o preenchimento acontece uma vez por montagem — sem efeito de sincronização.
 */
function ProductFormFields({
  mode,
  initial,
  isSubmitting,
  serverErrors,
  onSubmit,
  onCancel,
}: ProductFormFieldsProps) {
  const [values, setValues] = useState<ProductFormValues>(initial);
  const [errors, setErrors] = useState<FormErrors>({});
  const merged = { ...errors, ...serverErrors };

  const setField =
    (field: keyof ProductFormValues) =>
    (event: { target: { value: string } }) => {
      setValues((current) => ({ ...current, [field]: event.target.value }));
      setErrors((current) => ({ ...current, [field]: undefined }));
    };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const found = validate(values);
    if (Object.keys(found).length > 0) {
      setErrors(found);
      return;
    }
    await onSubmit(values);
  };

  return (
    <form onSubmit={handleSubmit} noValidate>
      <CardBody className="space-y-5 p-6">
        <Input
          label="Sku"
          value={values.sku}
          onChange={setField("sku")}
          error={merged.sku}
          autoComplete="off"
        />
        <Input
          label="Title"
          value={values.title}
          onChange={setField("title")}
          error={merged.title}
        />
        <Textarea
          label="Description"
          value={values.description}
          onChange={setField("description")}
          error={merged.description}
          placeholder="Descrição detalhada do produto"
        />
        <Input
          label="Price"
          inputMode="decimal"
          value={values.price}
          onChange={setField("price")}
          error={merged.price}
          placeholder="0,00"
        />
        <Input
          label="Stock"
          inputMode="numeric"
          value={values.stockQuantity}
          onChange={setField("stockQuantity")}
          error={merged.stockQuantity}
          placeholder="0"
        />
      </CardBody>

      <CardFooter>
        <Button variant="secondary" onClick={onCancel} disabled={isSubmitting}>
          Cancelar
        </Button>
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting
            ? "Salvando..."
            : mode === "create"
              ? "Criar"
              : "Salvar"}
        </Button>
      </CardFooter>
    </form>
  );
}

function toFormValues(product: ProductView): ProductFormValues {
  return {
    sku: product.sku,
    title: product.title,
    description: product.description,
    price: String(product.price),
    stockQuantity: String(product.stockQuantity),
  };
}

/**
 * Formulário de criação e edição de produto (Imagem 3).
 *
 * A mesma tela atende os dois casos: `/products/new` cria e
 * `/products/:id/edit` edita. Deslogado, ambas redirecionam para `/login` e
 * voltam aqui depois do login.
 */
export function ProductFormPage({ mode }: { mode: "create" | "edit" }) {
  const { id } = useParams();
  const productId = Number(id);
  const navigate = useNavigate();
  const { notify } = useToast();

  const existing = useProductView(productId);
  const createProduct = useCreateProduct();
  const updateProduct = useUpdateProduct();

  const [serverErrors, setServerErrors] = useState<FormErrors>({});
  const current = existing.product;

  const submit = async (values: ProductFormValues) => {
    setServerErrors({});
    const payload = {
      sku: values.sku.trim(),
      title: values.title.trim(),
      description: values.description.trim(),
      price: parseDecimal(values.price),
      stockQuantity: parseDecimal(values.stockQuantity || "0"),
    };

    try {
      if (mode === "create") {
        const created = await createProduct.mutateAsync(payload);
        notify({
          tone: "success",
          title: "Produto criado",
          description: created.title,
        });
        navigate(paths.productDetail(created.id));
        return;
      }

      if (!current) {
        return;
      }
      await updateProduct.mutateAsync({
        id: current.productId,
        skuId: current.skuId,
        ...payload,
      });
      notify({ tone: "success", title: "Produto atualizado" });
      navigate(paths.productDetail(current.productId));
    } catch (caught) {
      if (caught instanceof ApiError && caught.code === "conflict") {
        // SKU duplicado: erro de campo, não toast.
        setServerErrors({ sku: caught.message });
        return;
      }
      notify({
        tone: "error",
        title: "Não foi possível salvar o produto",
        description: caught instanceof ApiError ? caught.message : undefined,
      });
    }
  };

  if (mode === "edit" && existing.isPending) {
    return <LoadingBlock label="Carregando produto..." />;
  }

  if (mode === "edit" && !current) {
    return (
      <EmptyState
        title="Produto não encontrado"
        description="O produto pode ter sido removido."
      />
    );
  }

  // `key` remonta os campos quando o produto carrega, aplicando os valores
  // iniciais sem precisar de efeito.
  const formKey = mode === "edit" && current ? String(current.id) : "new";

  return (
    <div className="space-y-6">
      <PageHeader
        title={mode === "create" ? "Criar Produto" : "Editar Produto"}
        description={
          mode === "create"
            ? "Adicione um novo produto ao catálogo."
            : "Atualize as informações do produto."
        }
      />

      <Card className="mx-auto w-full max-w-2xl">
        <ProductFormFields
          key={formKey}
          mode={mode}
          initial={
            mode === "edit" && current
              ? toFormValues(current)
              : EMPTY_PRODUCT_FORM
          }
          isSubmitting={createProduct.isPending || updateProduct.isPending}
          serverErrors={serverErrors}
          onSubmit={submit}
          onCancel={() => navigate(-1)}
        />
      </Card>
    </div>
  );
}