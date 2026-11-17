// Connexion refaite dans le style v3 (même mécanisme d'authentification que l'app actuelle).
import { useState } from "react";

interface Props {
  onLogin: (email: string, password: string) => Promise<void>;
  onRegister: (email: string, password: string, name: string) => Promise<void>;
}

export default function LoginV3({ onLogin, onRegister }: Props) {
  const [inscription, setInscription] = useState(false);
  const [email, setEmail] = useState("");
  const [mdp, setMdp] = useState("");
  const [nom, setNom] = useState("");
  const [voir, setVoir] = useState(false);
  const [erreur, setErreur] = useState("");
  const [attente, setAttente] = useState(false);

  const soumettre = async (e: React.FormEvent) => {
    e.preventDefault();
    setErreur("");
    setAttente(true);
    try {
      if (inscription) await onRegister(email, mdp, nom);
      else await onLogin(email, mdp);
    } catch (err) {
      setErreur(err instanceof Error ? err.message : "Connexion impossible.");
    } finally {
      setAttente(false);
    }
  };

  const champ = "h-11 w-full rounded-lg border border-[var(--line)] bg-[var(--card)] px-3.5 text-[16px] min-[900px]:text-[15px] transition-colors champ";

  return (
    <main className="grid h-full grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      <section className="side hidden flex-col justify-between p-12 lg:flex">
        <span className="text-[17px] font-semibold tracking-[0.12em]">MARC</span>
        <div className="enter max-w-md">
          <p className="titre-serif text-[34px] leading-[1.08]">Dictez.<br />Le projet est prêt à relire.</p>
          <p className="side-mute mt-6 text-[15px] leading-relaxed">Chaque élément cite sa source dans la dictée. Chaque doute est signalé. Rien n'est inventé.</p>
        </div>
        <p className="side-mute text-[12px]">Une solution Gilbert</p>
      </section>
      <section className="scroll flex overflow-y-auto bg-[var(--paper)] px-6 py-8"><div className="m-auto w-full max-w-[380px]">
        <p className="mb-8 text-[17px] font-semibold tracking-[0.12em] lg:hidden">MARC</p>
        <form onSubmit={soumettre} className="enter w-full" aria-labelledby="titre-login">
          <h1 id="titre-login" className="titre-serif text-[28px] leading-tight">{inscription ? "Créer un compte" : "Se connecter"}</h1>
          <p className="mt-2 text-[15px] text-[var(--mute)]">Aide à la rédaction de comptes rendus d'anatomie et cytologie pathologiques.</p>
          <div className="mt-8 space-y-4 max-sm:mt-6">
            {inscription && (
              <label className="block">
                <span className="label">Nom complet</span>
                <input className={`${champ} mt-1.5`} value={nom} onChange={(e) => setNom(e.target.value)} required autoComplete="name" />
              </label>
            )}
            <label className="block">
              <span className="label">Adresse e-mail</span>
              <input className={`${champ} mt-1.5`} type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="username" autoFocus placeholder="nom@laboratoire.fr" />
            </label>
            <label className="block">
              <span className="label">Mot de passe</span>
              <span className="relative mt-1.5 block">
                <input className={`${champ} pr-24`} type={voir ? "text" : "password"} value={mdp} onChange={(e) => setMdp(e.target.value)} required minLength={8} autoComplete={inscription ? "new-password" : "current-password"} />
                <button type="button" onClick={() => setVoir(!voir)} aria-pressed={voir} className="absolute right-0.5 top-1/2 flex h-10 -translate-y-1/2 items-center rounded !px-3 text-[13px] text-[var(--mute)] hover:text-[var(--ink)]">
                  {voir ? "Masquer" : "Afficher"}
                </button>
              </span>
            </label>
          </div>
          {erreur && <p role="alert" className="mt-4 rounded-lg bg-[var(--red-soft)] px-3 py-2 text-[13px] text-[var(--red)]">{erreur}</p>}
          <button type="submit" disabled={attente} className="btn btn-primary mt-6 h-11 w-full justify-center text-[15px]">
            {attente ? "Connexion…" : inscription ? "Créer le compte" : "Continuer"}
          </button>
          <button type="button" onClick={() => { setInscription(!inscription); setErreur(""); }} className="mt-2 flex h-11 w-full items-center justify-center text-[13px] text-[var(--mute)] hover:text-[var(--ink)]">
            {inscription ? "Déjà un compte ? Se connecter" : "Pas de compte ? S'inscrire"}
          </button>
          <p className="mt-8 text-[12px] leading-relaxed text-[var(--faint)]">MARC est un outil d'aide à la rédaction, non un dispositif médical. Le praticien relit et valide seul le compte rendu.</p>
        </form>
      </div></section>
    </main>
  );
}
