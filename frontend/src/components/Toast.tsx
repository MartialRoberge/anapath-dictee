import { useState, useCallback, createContext, useContext } from "react";
import { X, AlertCircle, CheckCircle2, Info } from "lucide-react";

type ToastType = "success" | "error" | "info";

interface ToastItem {
  id: number;
  message: string;
  type: ToastType;
}

interface ToastContextValue {
  toast: (message: string, type?: ToastType) => void;
}

const ToastContext = createContext<ToastContextValue>({
  toast: () => {},
});

export function useToast() {
  return useContext(ToastContext);
}

let _nextId = 0;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const toast = useCallback((message: string, type: ToastType = "info") => {
    const id = ++_nextId;
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  }, []);

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      {/* Toast container */}
      <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-2 max-w-sm">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`
              animate-toast-in flex items-start gap-3 rounded-lg border px-4 py-3 shadow-lg
              ${t.type === "error" ? "border-destructive/30 bg-destructive/10 text-destructive" : ""}
              ${t.type === "success" ? "border-success/30 bg-success/10 text-success" : ""}
              ${t.type === "info" ? "border-primary/30 bg-primary/10 text-primary" : ""}
            `}
          >
            {t.type === "error" && <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />}
            {t.type === "success" && <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />}
            {t.type === "info" && <Info className="mt-0.5 h-4 w-4 shrink-0" />}
            <span className="flex-1 text-sm">{t.message}</span>
            <button
              onClick={() => dismiss(t.id)}
              className="shrink-0 opacity-60 hover:opacity-100"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
