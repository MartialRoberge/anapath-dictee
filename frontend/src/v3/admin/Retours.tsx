// Retours : flux unique (signalements, notes, avis, commentaires d'étude). Un signalement se traite sur place : statut et note admin.
import { useState } from "react";
import { CATEGORIES, dateHeure, NATURES, ORIGINES, STATUTS } from "./format";
import type { AdminApi, FiltresRetours, Origine, Retour, RetoursData, SignalementMaj, Statut } from "./types";
import { useCharge } from "./useCharge";

export const PAR_PAGE = 25;
const ORIGINES_FILTRE: [Origine | "", string][] = [["", "Toutes"], ["v3", "v3"], ["ancienne_version", "Ancienne version"], ["etude", "Étude"]];
const STATUTS_FILTRE: [Statut | "", string][] = [["", "Tous"], ["ouvert", "Ouvert"], ["en_cours", "En cours"], ["traite", "Traité"], ["rejete", "Rejeté"]];

function Qualite({ r }: { r: Retour }) {
  if (r.sens === "positif" && r.nature === "note") return <>Utile</>;
  if (r.sens === "negatif" && r.nature === "note") return <>À améliorer</>;
  if (r.note_sur_5) return <>{r.note_sur_5} / 5</>;
  return null;
}

/** Zone de traitement d'un signalement. `onEnregistrer` renvoie le signalement mis à jour. */
export function Traitement({ r, onEnregistrer, notePrecedente }: { r: Retour; onEnregistrer: (corps: { statut?: Statut; note_admin?: string }) => Promise<SignalementMaj>; notePrecedente?: string | null }) {
  const [statut, setStatut] = useState<Statut>(r.statut ?? "ouvert");
  const [note, setNote] = useState(notePrecedente ?? "");
  const [enCours, setEnCours] = useState(false);
  const [message, setMessage] = useState("");
  const enregistrer = async () => {
    setEnCours(true); setMessage("");
    try {
      const corps: { statut?: Statut; note_admin?: string } = {};
      if (statut !== r.statut) corps.statut = statut;
      if (note.trim() !== (notePrecedente ?? "").trim()) corps.note_admin = note.trim();
      if (!Object.keys(corps).length) { setMessage("Aucun changement."); return; }
      await onEnregistrer(corps);
      setMessage("Enregistré.");
    } catch (e) { setMessage((e as Error).message); }
    finally { setEnCours(false); }
  };
  return (
    <div className="mt-3 border-t pt-4" style={{ borderColor: "var(--a-line-soft)" }}>
      <div className="adm-seg" role="radiogroup" aria-label="Statut du signalement">
        {(Object.keys(STATUTS) as Statut[]).map((s) => <button key={s} type="button" role="radio" aria-checked={statut === s} className="adm-seg-item" onClick={() => setStatut(s)}>{STATUTS[s]}</button>)}
      </div>
      <label className="mt-3 block text-[12px] adm-doux" htmlFor={`note-${r.ref}`}>Note admin (1000 caractères au plus, visible des seuls administrateurs)</label>
      <textarea id={`note-${r.ref}`} className="adm-champ mt-1" rows={3} maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)} />
      <div className="mt-3 flex items-center justify-end gap-3">
        {message && <span role="status" className="text-[13px] adm-doux">{message}</span>}
        <button type="button" className="adm-btn adm-btn-primaire" disabled={enCours} onClick={enregistrer}>{enCours ? "Enregistrement…" : "Enregistrer"}</button>
      </div>
    </div>
  );
}

export function LigneRetour({ r, ouvert, onBascule, onEnregistrer, note }: {
  r: Retour; ouvert: boolean; onBascule: () => void; note?: string | null;
  onEnregistrer: (corps: { statut?: Statut; note_admin?: string }) => Promise<SignalementMaj>;
}) {
  const signalement = r.nature === "signalement";
  const meta = [ORIGINES[r.origine], NATURES[r.nature], r.categorie ? CATEGORIES[r.categorie] ?? r.categorie : null].filter(Boolean).join(" · ");
  const a = r.statut === "ouvert" || r.statut === "en_cours";
  return (
    <li className="py-4">
      <div className="flex items-start gap-4">
        <div className="min-w-0 flex-1">
          <div className="adm-label">{meta}</div>
          <p className="m-0 mt-1 whitespace-pre-wrap break-words text-[14px]">{r.message || <span className="adm-faible">(sans message)</span>}</p>
          <div className="mt-1 text-[12px] adm-doux">
            {r.utilisateur.nom ?? r.utilisateur.email ?? "Compte supprimé"} · {dateHeure(r.cree_le)}{(r.sens || r.note_sur_5) && <> · <Qualite r={r} /></>}
          </div>
        </div>
        {signalement && r.statut && (
          <button type="button" className="adm-btn adm-btn-sm shrink-0" aria-expanded={ouvert} onClick={onBascule}>
            <span className={a ? "adm-ambre" : ""}>{STATUTS[r.statut]}</span> <span aria-hidden>{ouvert ? "−" : "+"}</span><span className="adm-sr">{ouvert ? "Fermer le traitement" : "Traiter"}</span>
          </button>
        )}
      </div>
      {signalement && ouvert && <Traitement r={r} onEnregistrer={onEnregistrer} notePrecedente={note} />}
    </li>
  );
}

export function ListeRetours({ data, ouvertId, onBascule, onEnregistrer, notes }: {
  data: RetoursData; ouvertId: string | null; onBascule: (id: string) => void; notes: Record<string, string | null>;
  onEnregistrer: (r: Retour, corps: { statut?: Statut; note_admin?: string }) => Promise<SignalementMaj>;
}) {
  if (!data.items.length) return <p className="adm-carte m-0 adm-doux">Aucun retour pour ces filtres.</p>;
  return (
    <ul className="adm-carte adm-liste !py-0" aria-label="Retours">
      {data.items.map((r) => (
        <LigneRetour key={r.id} r={r} ouvert={ouvertId === r.id} note={notes[r.ref]} onBascule={() => onBascule(r.id)} onEnregistrer={(c) => onEnregistrer(r, c)} />
      ))}
    </ul>
  );
}

export default function Retours({ api }: { api: AdminApi }) {
  const [f, setF] = useState<FiltresRetours>({ origine: "", categorie: "", statut: "", page: 1 });
  const [ouvertId, setOuvertId] = useState<string | null>(null);
  const [notes, setNotes] = useState<Record<string, string | null>>({});
  const { data, setData, erreur } = useCharge(() => api.retours(f), [api, f]);
  const change = (p: Partial<FiltresRetours>) => { setOuvertId(null); setF({ ...f, page: 1, ...p }); };
  const enregistrer = async (r: Retour, corps: { statut?: Statut; note_admin?: string }) => {
    const maj = await api.majSignalement(r.ref, corps);
    setNotes((n) => ({ ...n, [r.ref]: maj.note_admin }));
    setData((d) => d && { ...d, items: d.items.map((x) => (x.id === r.id ? { ...x, statut: maj.statut } : x)) });
    return maj;
  };
  const debut = data ? (data.page - 1) * PAR_PAGE + 1 : 0;
  const fin = data ? Math.min(data.total, data.page * PAR_PAGE) : 0;
  return (
    <section aria-label="Retours">
      <div className="mb-6 flex flex-wrap items-end gap-x-6 gap-y-4">
        <div><div className="adm-label mb-1.5">Origine</div>
          <div className="adm-seg" role="radiogroup" aria-label="Origine">
            {ORIGINES_FILTRE.map(([k, l]) => <button key={k} type="button" role="radio" aria-checked={f.origine === k} className="adm-seg-item" onClick={() => change({ origine: k })}>{l}</button>)}
          </div></div>
        <div><div className="adm-label mb-1.5">Statut</div>
          <div className="adm-seg" role="radiogroup" aria-label="Statut">
            {STATUTS_FILTRE.map(([k, l]) => <button key={k} type="button" role="radio" aria-checked={f.statut === k} className="adm-seg-item" onClick={() => change({ statut: k })}>{l}</button>)}
          </div></div>
        <div className="min-w-[220px]"><label className="adm-label mb-1.5 block" htmlFor="filtre-categorie">Catégorie</label>
          <select id="filtre-categorie" className="adm-champ" value={f.categorie} onChange={(e) => change({ categorie: e.target.value })}>
            <option value="">Toutes</option>
            {Object.entries(CATEGORIES).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select></div>
      </div>
      {erreur && <p role="alert" className="adm-carte adm-erreur m-0">{erreur}</p>}
      {!data && !erreur && <p className="adm-doux">Chargement…</p>}
      {data && <ListeRetours data={data} ouvertId={ouvertId} notes={notes} onBascule={(id) => setOuvertId(ouvertId === id ? null : id)} onEnregistrer={enregistrer} />}
      {data && data.total > 0 && (
        <nav className="mt-4 flex items-center justify-between gap-3" aria-label="Pagination">
          <span className="num text-[13px] adm-doux">{debut}–{fin} sur {data.total}</span>
          <span className="flex gap-2">
            <button type="button" className="adm-btn" disabled={data.page <= 1} onClick={() => change({ page: data.page - 1 })}>Précédent</button>
            <button type="button" className="adm-btn" disabled={fin >= data.total} onClick={() => change({ page: data.page + 1 })}>Suivant</button>
          </span>
        </nav>
      )}
    </section>
  );
}
