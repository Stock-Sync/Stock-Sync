import { useCallback, useEffect, useRef, useState } from "react";

// Adiciona a tipagem global para o Cloudinary evitar erros do TypeScript
declare global {
  interface Window {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    cloudinary: any;
  }
}

interface CloudinaryUploaderProps {
  onUploadComplete: (urls: string[]) => void;
  maxFiles?: number;
  folder?: string;
}

export function CloudinaryUploader({
  onUploadComplete,
  maxFiles = 12,
  folder = "stocksync/products",
}: CloudinaryUploaderProps) {
  const [urls, setUrls] = useState<string[]>([]);
  const [isUploading, setIsUploading] = useState(false);

  // Carrega o script do Cloudinary globalmente se não estiver carregado
  useEffect(() => {
    if (!window.cloudinary) {
      const script = document.createElement("script");
      script.src = "https://widget.cloudinary.com/v2.0/global/all.js";
      script.async = true;
      document.body.appendChild(script);
      script.onerror = () => {
        console.error("Failed to load Cloudinary widget");
      };
    }
  }, []);

  // Chama onUploadComplete apenas quando a lista de URLs realmente muda,
  // evitando loops com props recriadas a cada render (ex.: arrow functions
  // inline no componente pai).
  const urlsRef = useRef(urls);
  useEffect(() => {
    const changed =
      urls.length !== urlsRef.current.length ||
      urls.some((url, i) => url !== urlsRef.current[i]);
    if (!changed) {
      return;
    }
    urlsRef.current = urls;
    onUploadComplete(urls);
  }, [onUploadComplete, urls]);

  const openWidget = useCallback(() => {
    if (!window.cloudinary) return;

    const widget = window.cloudinary.createUploadWidget(
      {
        cloudName: import.meta.env.VITE_CLOUDINARY_CLOUD_NAME,
        uploadPreset: import.meta.env.VITE_CLOUDINARY_UPLOAD_PRESET,
        folder: folder,
        maxFiles: maxFiles - urls.length, // Respeita o limite restante de arquivos
        multiple: true,
        resourceType: "image",
        clientAllowedFormats: ["jpg", "jpeg", "png", "webp"],
        maxFileSize: 10000000,
        showPoweredBy: false,
        styles: {
          palette: {
            window: "#FFFFFF",
            windowBorder: "#E5E7EB",
            tabIcon: "#6366F1",
            menuIcons: "#6B7280",
            textDark: "#1F2937",
            textLight: "#FFFFFF",
            link: "#6366F1",
            action: "#6366F1",
            inactiveTabIcon: "#9CA3AF",
            error: "#EF4444",
            inProgress: "#6366F1",
            complete: "#10B981",
            sourceBg: "#F9FAFB",
          },
          fonts: {
            default: '"Inter", sans-serif',
          },
        },
      },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (error: any, result: any) => {
        if (error) {
          console.error("Cloudinary upload error:", error);
          setIsUploading(false);
          return;
        }

        // Quando um arquivo termina de ser enviado com sucesso
        if (result && result.event === "success") {
          setUrls((prev) => [...prev, result.info.secure_url]);
        }

        // Quando o usuário fecha o widget
        if (result && result.event === "close") {
          setIsUploading(false);
        }
      }
    );

    setIsUploading(true);
    widget.open();
  }, [folder, maxFiles, urls.length]);

  const handleRemove = (urlToRemove: string) => {
    const updatedUrls = urls.filter((url) => url !== urlToRemove);
    setUrls(updatedUrls);
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-sm text-slate-600">
          {urls.length}/{maxFiles} imagens
        </span>
      </div>

      <button
        type="button"
        onClick={openWidget}
        disabled={isUploading || urls.length >= maxFiles || !window.cloudinary}
        className="relative w-16 h-16 rounded-lg border-2 border-dashed border-slate-300 flex items-center justify-center bg-slate-50 hover:border-brand-500 hover:bg-brand-50 transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <svg className="h-6 w-6 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 14l-2.586-2.586a2 2 0 012.828 0L20 22M4 4l16 16" />
        </svg>
        <span className="text-center text-xs text-slate-500">+ Adicionar</span>
      </button>

      {urls.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {urls.map((url, i) => (
            <div key={i} className="relative w-16 h-16 rounded-lg border border-line overflow-hidden">
              <img src={url} alt={`Imagem ${i + 1}`} className="w-full h-full object-cover" />
              <button
                type="button"
                onClick={() => handleRemove(url)}
                className="absolute top-1 right-1 rounded-full bg-red-500 text-white text-xs p-1 hover:bg-red-600"
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}