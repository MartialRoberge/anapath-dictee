// Commande de dictée intégrée au pied de la zone de saisie de « Nouveau projet » : un seul bouton, un seul état visible.
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
    <div className="flex min-w-0 flex-1 items-center gap-3" role="group" aria-label="Dictée vocale">
      <button
        type="button" onClick={onBasculer} disabled={occupe || etat === "demande"} aria-pressed={enr}
        className={`btn min-w-[104px] ${enr ? "btn-blue" : "btn-primary"}`}
      >
        {enr ? "Envoyer" : "Dicter"}
      </button>
      <div className="min-w-0 flex-1" aria-live="polite">
        {enr ? (
          <p className="flex flex-wrap items-center gap-x-2 text-[15px]">
            <span className="enregistrement-point" aria-hidden />
            <span className="num font-medium">{chrono(secondes)}</span>
            <span className="text-[var(--mute)]">Relâchez <span className="kbd">Espace</span> pour envoyer</span>
          </p>
        ) : etat === "demande" ? (
          <p className="text-[13px] text-[var(--mute)]">Autorisez le micro dans votre navigateur…</p>
        ) : (
          <p className="text-[13px] leading-snug text-[var(--mute)]">ou maintenez <span className="kbd">Espace</span> et parlez</p>
        )}
      </div>
      {enr && <button type="button" onClick={onAnnuler} className="btn btn-ghost btn-sm">Annuler <span className="kbd">Échap</span></button>}
    </div>
  );
}
