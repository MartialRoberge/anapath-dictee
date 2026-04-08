import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-screen items-center justify-center bg-background p-8">
          <div className="max-w-md space-y-4 text-center">
            <h1 className="text-2xl font-bold text-foreground">
              Une erreur est survenue
            </h1>
            <p className="text-muted-foreground">
              L&apos;application a rencontre un probleme inattendu.
            </p>
            {this.state.error && (
              <p className="rounded bg-destructive/10 p-2 text-sm text-destructive">
                {this.state.error.message}
              </p>
            )}
            <button
              onClick={() => window.location.reload()}
              className="rounded bg-primary px-4 py-2 text-primary-foreground hover:bg-primary/90"
            >
              Recharger l&apos;application
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
