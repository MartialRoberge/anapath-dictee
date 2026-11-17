// Centre pendant la génération et en cas d'erreur : états réels uniquement.
import { useEffect, useState } from "react";
import type { EtatGeneration } from "../hooks/useGeneration";

function Chrono({ debut }: { debut: number }) {
  const [t, setT] = useState(0);
  useEffect(() => {
    const i = setInterval(() => setT(Date.now() - debut), 100);
    return () => clearInterval(i);
  }, [debut]);
  return <span className="num">{(t / 1000).toFixed(1).replace(".", ",")} s</span>;
}

interface Props { etat: EtatGeneration; onReessayer: () => void; onAnnuler: () => void; onNouveau: () => void }

export default function EtatCentre({ etat, onReessayer, onAnnuler, onNouveau }: Props) {
  if (etat.phase === "erreur") {
    return (
      <div className="enter mx-auto max-w-[620px] pt-[12vh]" role="alert">
        <p className="label">Le traitement n'a pas abouti</p>
        <h1 className="titre-serif mt-3 text-[34px] leading-tight">{etat.erreur?.recuperable ? "Un incident est survenu." : "Impossible de continuer."}</h1>
        <p className="mt-4 text-[14.5px] leading-relaxed text-[var(--mute)]">{etat.erreur?.message}</p>
        {etat.dictee && <p className="mt-2 text-[13px] text-[var(--faint)]">Votre dictée est conservée à l'écran, rien n'a été enregistré sur le serveur.</p>}
        <div className="mt-7 flex gap-2.5">
          {etat.erreur?.recuperable && <button type="button" className="btn btn-primary" onClick={onReessayer}>Réessayer</button>}
          <button type="button" className="btn" onClick={onNouveau}>Revenir à la dictée</button>
        </div>
      </div>
    );
  }
  const apercu = etat.partiel;
  return (
    <div className="enter mx-auto max-w-[680px] pt-[10vh]" aria-busy="true">
      <p className="label">{etat.mode === "iteration" ? "Complément en cours d'intégration" : "Projet en préparation"}</p>
      <h1 className="titre-serif mt-3 text-[34px] leading-tight">{apercu.length ? "Rédaction du projet" : etat.etapes.length ? "Analyse de la dictée" : etat.audio ? "Envoi de l'enregistrement" : "Envoi de la dictée"}</h1>
      <p className="mt-3 flex items-center gap-3 text-[13px] text-[var(--mute)]" role="status">
        <span>Temps écoulé <Chrono debut={etat.debut} /></span>
        <button type="button" className="underline underline-offset-2 hover:text-[var(--ink)]" onClick={onAnnuler}>Annuler</button>
      </p>
      {etat.dictee && !etat.audio && (
        <div className="carte mt-8 p-5">
          <p className="label mb-2">Dictée</p>
          <p className="line-clamp-6 text-[14px] leading-[1.7] text-[var(--mute)]">{etat.dictee}</p>
        </div>
      )}
      {apercu.length > 0 && (
        <div className="carte doc mt-6 p-6">
          <p className="label mb-3">Aperçu de la rédaction</p>
          {apercu.filter((e) => e.type !== "trou").map((e) => <p key={e.id} className="fade py-0.5">{e.texte}</p>)}
        </div>
      )}
      {apercu.length === 0 && <div className="mt-8 space-y-2.5" aria-hidden><div className="skeleton h-3.5 w-[92%]" /><div className="skeleton h-3.5 w-[78%]" /><div className="skeleton h-3.5 w-[64%]" /></div>}
    </div>
  );
}
