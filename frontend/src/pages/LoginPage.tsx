import { useState } from "react";
import { IrisLogo } from "../components/IrisLogo";
import { Button } from "@/components/ui/button";
import { Eye, EyeOff } from "lucide-react";

interface LoginPageProps {
  onLogin: (email: string, password: string) => Promise<void>;
  onRegister: (email: string, password: string, name: string) => Promise<void>;
}

export default function LoginPage({ onLogin, onRegister }: LoginPageProps) {
  const [isRegister, setIsRegister] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      if (isRegister) {
        await onRegister(email, password, name);
      } else {
        await onLogin(email, password);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Erreur de connexion");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-background iris-botanical-glow">
      {/* Botanical background pattern */}
      <div className="absolute inset-0 iris-bg-pattern" />

      {/* Decorative botanical SVG — leaf veins and cell structures */}
      <svg className="absolute inset-0 h-full w-full opacity-[0.025] pointer-events-none" preserveAspectRatio="xMidYMid slice" viewBox="0 0 800 600">
        <path d="M50 300 Q200 200 350 300 Q500 400 650 300" stroke="currentColor" strokeWidth="1" fill="none" />
        <path d="M50 350 Q200 280 350 350 Q500 420 650 350" stroke="currentColor" strokeWidth="0.5" fill="none" />
        <path d="M100 100 Q250 180 400 100" stroke="currentColor" strokeWidth="0.8" fill="none" />
        <path d="M400 500 Q550 420 700 500" stroke="currentColor" strokeWidth="0.8" fill="none" />
        <circle cx="150" cy="150" r="40" stroke="currentColor" strokeWidth="0.5" fill="none" />
        <circle cx="600" cy="400" r="60" stroke="currentColor" strokeWidth="0.5" fill="none" />
        <circle cx="700" cy="150" r="30" stroke="currentColor" strokeWidth="0.5" fill="none" />
        <circle cx="100" cy="450" r="50" stroke="currentColor" strokeWidth="0.5" fill="none" />
      </svg>

      {/* Login card */}
      <div className="relative z-10 mx-4 w-full max-w-md animate-fade-in">
        <div className="rounded-2xl border bg-card/80 backdrop-blur-sm p-8 shadow-xl">
          {/* Brand */}
          <div className="mb-8 flex flex-col items-center gap-3">
            <IrisLogo size={48} className="animate-float" />
            <h1 className="text-3xl font-bold tracking-tight text-iris-700 dark:text-iris-400">
              Iris
            </h1>
            <p className="text-center text-sm text-muted-foreground leading-relaxed">
              Comptes rendus anatomopathologiques<br />
              structures par intelligence artificielle
            </p>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            {isRegister && (
              <div>
                <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
                  Nom complet
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                  className="w-full rounded-lg border bg-background px-3.5 py-2.5 text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-ring"
                  placeholder="Dr. Martin Dupont"
                />
              </div>
            )}

            <div>
              <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
                Adresse email
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full rounded-lg border bg-background px-3.5 py-2.5 text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-ring"
                placeholder="nom@laboratoire.fr"
              />
            </div>

            <div>
              <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
                Mot de passe
              </label>
              <div className="relative">
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={8}
                  className="w-full rounded-lg border bg-background px-3.5 py-2.5 pr-10 text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-ring"
                  placeholder="8 caracteres minimum"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            {error && (
              <p className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {error}
              </p>
            )}

            <Button
              type="submit"
              className="w-full bg-iris-600 hover:bg-iris-700 text-white font-medium h-11"
              disabled={loading}
            >
              {loading ? "..." : isRegister ? "Creer un compte" : "Se connecter"}
            </Button>
          </form>

          {/* Toggle */}
          <div className="mt-6 text-center">
            <button
              type="button"
              onClick={() => { setIsRegister(!isRegister); setError(""); }}
              className="text-sm text-muted-foreground hover:text-primary transition-colors"
            >
              {isRegister ? "Deja un compte ? Se connecter" : "Pas de compte ? S'inscrire"}
            </button>
          </div>
        </div>

        {/* Disclaimer */}
        <p className="mt-4 text-center text-[10px] text-muted-foreground/40 leading-relaxed">
          Iris est un outil d'aide a la redaction. Il ne constitue pas un dispositif medical.<br />
          Le praticien reste seul responsable du contenu du compte-rendu.
        </p>
      </div>
    </div>
  );
}
