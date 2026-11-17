import { StrictMode, lazy, Suspense } from "react";
import { createRoot } from "react-dom/client";
import { ErrorBoundary } from "./components/ErrorBoundary";
import "./index.css";

// MARC v3 est l'unique application montée à la racine.
const V3App = lazy(() => import("./v3/V3App"));

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Root element not found");
}

createRoot(rootElement).render(
  <StrictMode>
    <ErrorBoundary>
      <Suspense fallback={null}>
        <V3App />
      </Suspense>
    </ErrorBoundary>
  </StrictMode>
);
