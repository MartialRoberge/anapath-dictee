// Feuille « Signaler » : l'unique entrée pour remonter un dysfonctionnement, une erreur, une idée ou une non-conformité.
// Aucune donnée patient : le message est libre mais avertissement visible, et le serveur refuse ce qui y ressemble.
import { useEffect, useRef, useState } from "react";
import "../admin/admin.css";
import {
  AVERTISSEMENT_PATIENT, CATEGORIES_SIGNALEMENT, envoyerSignalement, MESSAGE_DOUBLON, MESSAGE_ENVOYE, MESSAGE_MAX,
  type CategorieSignalement, type SignalementEnvoye,
} from "../lib/signalement";

interface VueProps {
  categorie: CategorieSignalement;
  message: string;
  erreur: string;
  enCours: boolean;
  /** Réponse du serveur une fois l'envoi réussi. */
  resultat: SignalementEnvoye | null;
  onCategorie: (c: CategorieSignalement) => void;
  onMessage: (m: string) => void;
  onEnvoyer: () => void;
  onFermer: () => void;
}

/** Partie présentationnelle (rendue à l'identique côté serveur dans les tests). */
export function FeuilleSignalementVue(p: VueProps) {
  const zone = useRef<HTMLTextAreaElement>(null);
  const fermer = useRef<HTMLButtonElement>(null);
  useEffect(() => { (p.resultat ? fermer : zone).current?.focus(); }, [p.resultat]);
  const clavier = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); p.onFermer(); }
  };
  const vide = p.message.trim().length === 0;
  return (
    <div className="adm-t adm-voile" onMouseDown={(e) => { if (e.target === e.currentTarget) p.onFermer(); }}>
      <div role="dialog" aria-modal="true" aria-labelledby="titre-signaler" onKeyDown={clavier} className="adm-feuille">
        <h2 id="titre-signaler" className="adm-serif m-0 text-[24px] leading-tight">Signaler</h2>
        {p.resultat ? (
          <>
            <p role="status" className="mt-4 text-[15px]">{p.resultat.doublon_de ? MESSAGE_DOUBLON : MESSAGE_ENVOYE}</p>
            <div className="mt-6 flex justify-end">
              <button ref={fermer} type="button" className="adm-btn adm-btn-primaire" onClick={p.onFermer}>Fermer</button>
            </div>
          </>
        ) : (
          <>
            <div className="adm-seg adm-seg-plein mt-4" role="radiogroup" aria-label="Catégorie du signalement">
              {CATEGORIES_SIGNALEMENT.map(([k, l]) => (
                <button key={k} type="button" role="radio" aria-checked={p.categorie === k} className="adm-seg-item" onClick={() => p.onCategorie(k)}>{l}</button>
              ))}
            </div>
            <label className="mt-4 block text-[13px] adm-doux" htmlFor="message-signalement">Que s'est-il passé ?</label>
            <textarea
              id="message-signalement" ref={zone} rows={5} maxLength={MESSAGE_MAX} value={p.message} className="adm-champ mt-1.5 block"
              aria-describedby="avert-patient" onChange={(e) => p.onMessage(e.target.value)}
            />
            <div className="mt-1.5 flex items-start justify-between gap-3">
              <p id="avert-patient" className="adm-avert">{AVERTISSEMENT_PATIENT}</p>
              <span className="num shrink-0 text-[12px] adm-faible">{p.message.length} / {MESSAGE_MAX}</span>
            </div>
            {p.erreur && <p role="alert" className="mt-3 text-[13px] adm-erreur">{p.erreur}</p>}
            <div className="mt-5 flex justify-end gap-2">
              <button type="button" className="adm-btn" onClick={p.onFermer}>Annuler</button>
              <button type="button" className="adm-btn adm-btn-primaire" disabled={vide || p.enCours} onClick={p.onEnvoyer}>{p.enCours ? "Envoi…" : "Envoyer"}</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

interface Props {
  categorieInitiale?: CategorieSignalement;
  projetId?: string;
  ecran: string;
  onFermer: () => void;
}

export default function FeuilleSignalement({ categorieInitiale = "dysfonctionnement", projetId, ecran, onFermer }: Props) {
  const [categorie, setCategorie] = useState<CategorieSignalement>(categorieInitiale);
  const [message, setMessage] = useState("");
  const [erreur, setErreur] = useState("");
  const [enCours, setEnCours] = useState(false);
  const [resultat, setResultat] = useState<SignalementEnvoye | null>(null);
  // Rend le focus à l'élément qui a ouvert la feuille.
  useEffect(() => {
    const avant = document.activeElement as HTMLElement | null;
    return () => { if (avant && document.contains(avant)) avant.focus(); };
  }, []);
  const envoyer = async () => {
    setEnCours(true); setErreur("");
    try { setResultat(await envoyerSignalement({ categorie, message, projet_id: projetId, ecran })); }
    catch (e) { setErreur((e as Error).message); }
    finally { setEnCours(false); }
  };
  return (
    <FeuilleSignalementVue
      categorie={categorie} message={message} erreur={erreur} enCours={enCours} resultat={resultat}
      onCategorie={setCategorie} onMessage={(m) => { setMessage(m); setErreur(""); }} onEnvoyer={envoyer} onFermer={onFermer}
    />
  );
}
