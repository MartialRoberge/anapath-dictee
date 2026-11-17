// Barre de dictée en bas de l'espace « Nouveau projet ».
import { chrono } from "../lib/format";

interface Props {
  etat: "repos" | "demande" | "enregistre";
  secondes: number;
  occupe: boolean;
  onBasculer: () => void;
  onAnnuler: () => void;
}

export default function BarreDictee({ etat, secondes, occupe, onBasculer, onAnnuler }: Props) {
  const enr = etat === "enregistre";
  return (
    <div className="pointer-events-none absolute inset-x-0 bottom-0 flex justify-center px-6 pb-6 pt-10 [background:linear-gradient(to_top,var(--paper)_55%,transparent)]">
      <div className="carte pointer-events-auto flex w-full max-w-[760px] items-center gap-4 p-2.5 pr-5 shadow-[0_8px_24px_-12px_rgba(14,14,14,0.2)]" role="group" aria-label="Dictée vocale">
        <button
          type="button" onClick={onBasculer} disabled={occupe || etat === "demande"} aria-pressed={enr}
          className={`btn h-10 min-w-[104px] justify-center px-5 text-[14px] ${enr ? "btn-blue" : "btn-primary"}`}
        >
          {enr ? "Envoyer" : "Dicter"}
        </button>
        <div className="min-w-0 flex-1" aria-live="polite">
          {enr ? (
            <p className="flex items-center gap-2 text-[14px]">
              <span className="enregistrement-point" aria-hidden />
              <span className="num font-medium">{chrono(secondes)}</span>
              <span className="text-[var(--mute)]">Relâchez <span className="kbd">Espace</span> pour envoyer</span>
            </p>
          ) : etat === "demande" ? (
            <p className="text-[14px] text-[var(--mute)]">Autorisez le micro dans votre navigateur…</p>
          ) : (
            <p className="text-[13.5px] text-[var(--mute)]">Maintenez <span className="kbd">Espace</span> pour dicter, relâchez pour envoyer. Pédale : même touche.</p>
          )}
        </div>
        {enr && <button type="button" onClick={onAnnuler} className="btn btn-ghost btn-sm">Annuler <span className="kbd">Échap</span></button>}
      </div>
    </div>
  );
}
