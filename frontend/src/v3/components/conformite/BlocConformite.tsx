// Bloc conformité ISO 15189:2022 dans la barre d'actions : statut brouillon/validé, validation par un
// pathologiste habilité, traçabilité consultable, entrée « Signaler ». Aucune donnée médicale n'est envoyée.
import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  blocages, DEROGATIONS, enregistrerGeneration, moi, sha256Hex,
  texteFinal, validerProjet, type Derogation, type ValidationEnregistree,
} from "../../lib/conformite";
import type { ProjetLocal } from "../../lib/session";
import { ACTION, touche } from "../../lib/raccourcis";
import { useDialogue } from "../../hooks/useDialogue";

type Volet = "valider" | "tracabilite" | null;

// Dernière validation connue par projet (mémoire de la session ; la preuve opposable est le journal serveur).
const validees = new Map<string, ValidationEnregistree>();

function Popover({ titre, onFermer, children }: { titre: string; onFermer: () => void; children: ReactNode }) {
  const racine = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const avant = document.activeElement as HTMLElement | null;
    return () => { if (avant && document.contains(avant)) avant.focus(); };
  }, []);
  useEffect(() => {
    const f = (e: MouseEvent) => { if (!racine.current?.contains(e.target as Node)) onFermer(); };
    document.addEventListener("mousedown", f);
    return () => document.removeEventListener("mousedown", f);
  }, [onFermer]);
  return (
    <>
      <div className="pop-scrim" aria-hidden />
      <div ref={racine} className="pop pop-tel bottom-full right-0 mb-2 !w-[380px] !max-w-[92vw] p-3" role="dialog" aria-label={titre} onKeyDown={(e) => e.key === "Escape" && onFermer()}>
        <div className="flex items-center pb-1.5"><p className="label flex-1">{titre}</p><button type="button" className="btn btn-ghost btn-sm pop-fermer -mr-3" onClick={onFermer}>Fermer</button></div>
        {children}
      </div>
    </>
  );
}

export interface ActionFeuille { titre: string; detail?: string; onClick: () => void; disabled?: boolean }

/** Feuille « Actions » du téléphone : statut en tête, puis les actions secondaires en liste (pas d'icônes). */
function FeuilleActions({ statut, actions, onFermer }: { statut: ReactNode; actions: ActionFeuille[]; onFermer: () => void }) {
  const racine = useRef<HTMLDivElement>(null);
  useDialogue(racine, onFermer);
  return (
    <div className="modal" onMouseDown={(e) => { if (e.target === e.currentTarget) onFermer(); }}>
      <div ref={racine} role="dialog" aria-modal="true" aria-labelledby="titre-actions" className="px-5 !pt-5">
        <div className="flex items-center gap-3">
          <h2 id="titre-actions" className="titre-serif flex-1 text-[22px] leading-[1.2]">Actions</h2>
          <button type="button" className="btn btn-ghost btn-sm" onClick={onFermer}>Fermer</button>
        </div>
        <p className="mt-1 text-[13px] leading-snug text-[var(--mute)]" role="status">{statut}</p>
        <ul className="mt-3">
          {actions.map((a) => (
            <li key={a.titre} className="border-t border-[var(--line-soft)] first:border-t-0">
              <button type="button" className="ligne-action" disabled={a.disabled} onClick={a.onClick}>
                <span className="text-[16px] font-medium">{a.titre}</span>
                {a.detail && <span className="text-[13px] text-[var(--mute)]">{a.detail}</span>}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

const Ligne = ({ k, v }: { k: string; v?: string }) => (
  <div className="flex gap-2 py-0.5 text-[12.5px]"><dt className="w-[132px] shrink-0 text-[var(--faint)]">{k}</dt><dd className="num break-all text-[var(--ink)]">{v || "—"}</dd></div>
);

interface PropsBloc {
  local: ProjetLocal; occupe: boolean; onSignaler: () => void; resume?: ReactNode; avant?: ReactNode; apres?: ReactNode; fin?: ReactNode;
  /** Téléphone : une seule ligne (Actions + Valider) ; `actions` alimente la feuille. */
  compact?: boolean; actions?: ActionFeuille[];
  /** Compact seulement : éléments insérés entre « Actions » et « Valider » (paysage : statut et Raisonnement). */
  enLigne?: ReactNode;
}

export default function BlocConformite({ local, occupe, onSignaler, resume, avant, apres, fin, compact, actions, enLigne }: PropsBloc) {
  const [volet, setVolet] = useState<Volet>(null);
  const [feuille, setFeuille] = useState(false);
  const [habilite, setHabilite] = useState<boolean | null>(null);
  const [empreinte, setEmpreinte] = useState("");
  const [derog, setDerog] = useState<Derogation | "">("");
  const [erreur, setErreur] = useState("");
  const [enCours, setEnCours] = useState(false);
  const [, rafraichir] = useState(0);
  const id = local.projet.id;
  const validation = validees.get(id);
  const b = blocages(local);
  const bloque = b.alertes_bloquantes + b.trous_obligatoires > 0;
  const t = local.projet.tracabilite;

  useEffect(() => { if (!occupe) void enregistrerGeneration(local.projet); }, [occupe, local.projet]);
  useEffect(() => { moi().then((m) => setHabilite(m.habilite)).catch(() => setHabilite(null)); }, []);
  useEffect(() => {
    let vivant = true;
    sha256Hex(texteFinal(local)).then((h) => vivant && setEmpreinte(h)).catch(() => vivant && setEmpreinte(""));
    return () => { vivant = false; };
  }, [local]);

  useEffect(() => {
    const f = (e: Event) => { if ((e as CustomEvent).detail === "valider") { setErreur(""); setVolet("valider"); } };
    window.addEventListener(ACTION, f);
    return () => window.removeEventListener(ACTION, f);
  }, []);

  const modifie = !!validation && !!empreinte && validation.empreinte_sha256 !== empreinte;
  const estValide = !!validation && !modifie;
  const ouvrir = (v: Exclude<Volet, null>) => { setErreur(""); setVolet(volet === v ? null : v); };

  const valider = async () => {
    setEnCours(true); setErreur("");
    try {
      const v = await validerProjet(local, empreinte, derog || undefined);
      validees.set(id, v); setVolet(null); setDerog(""); rafraichir((n) => n + 1);
    } catch (e) {
      setErreur((e as Error).message);
    } finally { setEnCours(false); }
  };

  const libelleValider = modifie ? "Revalider le compte rendu" : estValide ? "Compte rendu validé" : "Valider le compte rendu";
  const statut = estValide
    ? <>Validé par le pathologiste · révision {validation.revision}</>
    : modifie ? <b className="font-semibold text-[var(--amber)]">Modifié depuis la validation · à revalider</b>
    : habilite === false ? "Validation : pathologiste habilité" : "À valider par le pathologiste";

  return (
    <div className="relative" aria-label="Conformité du compte rendu">
      {compact ? (
        <div className="flex items-center gap-2">
          <button type="button" className="btn shrink-0" aria-haspopup="dialog" aria-expanded={feuille} onClick={() => setFeuille(true)}>Actions</button>
          {enLigne}
          <button type="button" className="btn btn-blue min-w-0 flex-1" disabled={occupe || estValide || habilite === false} aria-expanded={volet === "valider"}
            title={habilite === false ? "Réservé aux pathologistes habilités" : undefined} onClick={() => ouvrir("valider")}>{libelleValider}</button>
        </div>
      ) : (<>
      <div className="flex items-center gap-1">
        <p className="mr-auto min-w-0 flex-1 truncate text-[12.5px] text-[var(--mute)]" role="status">
          {resume}
          {resume && <span aria-hidden> · </span>}
          {estValide
            ? <>Validé par le pathologiste · révision {validation.revision}</>
            : modifie ? <b className="font-semibold text-[var(--amber)]">Modifié depuis la validation · à revalider</b>
            : habilite === false ? "Validation : pathologiste habilité" : "À valider par le pathologiste"}
        </p>
        <button type="button" className="btn btn-ghost btn-sm shrink-0" aria-expanded={volet === "tracabilite"} onClick={() => ouvrir("tracabilite")}>Traçabilité</button>
        <button type="button" className="btn btn-ghost btn-sm shrink-0" aria-haspopup="dialog" onClick={onSignaler}>Signaler</button>
        {apres}
      </div>
      <div className="mt-2.5 flex flex-wrap items-center justify-end gap-2">
        {avant}
        <button type="button" className="btn btn-blue" disabled={occupe || estValide || habilite === false} aria-expanded={volet === "valider"} aria-keyshortcuts="Alt+V"
          title={habilite === false ? "Réservé aux pathologistes habilités" : undefined} onClick={() => ouvrir("valider")}>
          {modifie ? "Revalider le compte rendu" : estValide ? "Compte rendu validé" : "Valider le compte rendu"} {!estValide && <span className="kbd">{touche("V")}</span>}
        </button>
        {fin}
      </div>
      </>)}

      {feuille && (
        <FeuilleActions
          statut={<>{resume}{resume && <span aria-hidden> · </span>}{statut}</>}
          onFermer={() => setFeuille(false)}
          actions={[
            ...(actions ?? []).map((a) => ({ ...a, onClick: () => { setFeuille(false); a.onClick(); } })),
            { titre: "Traçabilité", detail: "Versions, empreintes, statut du compte rendu", onClick: () => { setFeuille(false); setErreur(""); setVolet("tracabilite"); } },
            { titre: "Signaler", detail: "Un problème, une erreur ou une idée", onClick: () => { setFeuille(false); onSignaler(); } },
          ]}
        />
      )}

      {volet === "valider" && (
        <Popover titre="Valider le compte rendu" onFermer={() => setVolet(null)}>
          <p className="pb-2 text-[12.5px] text-[var(--mute)]">Vous attestez avoir relu ce compte rendu. Seule son empreinte, vos identifiants et les versions utilisées sont enregistrées, jamais le texte.</p>
          {bloque && (
            <div className="mb-2 rounded border border-[var(--amber-line)] bg-[var(--amber-soft)] p-2 text-[12.5px]" role="alert">
              <b>Blocages ouverts :</b> {b.alertes_bloquantes > 0 && `${b.alertes_bloquantes} alerte${b.alertes_bloquantes > 1 ? "s" : ""} bloquante${b.alertes_bloquantes > 1 ? "s" : ""}`}
              {b.alertes_bloquantes > 0 && b.trous_obligatoires > 0 && " · "}
              {b.trous_obligatoires > 0 && `${b.trous_obligatoires} trou${b.trous_obligatoires > 1 ? "s" : ""} obligatoire${b.trous_obligatoires > 1 ? "s" : ""}`}.
              <label className="mt-1.5 block text-[var(--mute)]">Dérogation motivée
                <select autoFocus className="mt-1 block w-full rounded border border-[var(--line)] bg-white p-1.5 text-[12.5px]" value={derog} onChange={(e) => setDerog(e.target.value as Derogation | "")}>
                  <option value="">Aucune : je traite les blocages d'abord</option>
                  {DEROGATIONS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                </select>
              </label>
            </div>
          )}
          {erreur && <p className="pb-2 text-[12.5px] text-[var(--red)]" role="alert">{erreur}</p>}
          <div className="flex justify-end gap-2">
            <button type="button" className="btn btn-sm" onClick={() => setVolet(null)}>Annuler</button>
            <button type="button" autoFocus={!bloque} className="btn btn-sm btn-primary" disabled={enCours || !empreinte || (bloque && !derog)} onClick={valider}>{enCours ? "Validation…" : "Valider"}</button>
          </div>
        </Popover>
      )}

      {volet === "tracabilite" && (
        <Popover titre="Traçabilité" onFermer={() => setVolet(null)}>
          {t ? (
            <dl>
              <Ligne k="Identifiant" v={t.id || id} />
              <Ligne k="Généré (UTC)" v={t.horodatage_utc} />
              <Ligne k="Pipeline" v={t.version_pipeline} />
              <Ligne k="Base de connaissances" v={`${t.kb_version ?? ""}${t.kb_statut === "en_service" ? " (en service)" : t.kb_statut === "non_en_service" ? " (hors service)" : ""}`} />
              <Ligne k="Empreinte base" v={t.kb_empreinte_sha256?.slice(0, 16)} />
              <Ligne k="Modèles" v={Object.entries(t.modeles ?? {}).map(([k, m]) => `${k} : ${m}`).join(" · ")} />
              <Ligne k="Empreinte dictée" v={t.empreinte_dictee_corrigee_sha256?.slice(0, 16)} />
              <Ligne k="Niveau de service" v={t.niveau_service} />
              <Ligne k="Empreinte texte actuel" v={empreinte.slice(0, 16)} />
              <Ligne k="Statut" v={estValide ? `validé (révision ${validation?.revision})` : "brouillon"} />
            </dl>
          ) : <p className="text-[12.5px] text-[var(--mute)]">Aucune information de traçabilité pour ce projet.</p>}
        </Popover>
      )}

    </div>
  );
}
