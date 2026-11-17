import { StrictMode, lazy, Suspense } from "react";
import { createRoot } from "react-dom/client";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { ToastProvider } from "./components/Toast";
import "./index.css";

// MARC v3 est montée à la racine. L'ancienne app reste accessible sous ?legacy=1 le temps de la transition.
const legacy = new URLSearchParams(window.location.search).get("legacy") === "1";
const App = lazy(() => import("./App"));
const V3App = lazy(() => import("./v3/V3App"));

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Root element not found");
}

createRoot(rootElement).render(
  <StrictMode>
    <ErrorBoundary>
      <ToastProvider>
        <Suspense fallback={null}>{legacy ? <App /> : <V3App />}</Suspense>
      </ToastProvider>
    </ErrorBoundary>
  </StrictMode>
);
