// Compléter par la voix : dictée d'appoint (micro ou texte) -> /v3/projets/iterer.
// L'enregistrement est transcrit puis laissé à la relecture avant envoi (jamais d'envoi à l'aveugle).
import { useCallback, useEffect, useRef, useState } from "react";
import { useDialogue } from "../hooks/useDialogue";
import { transcrire } from "../lib/api";
import { useRecorder } from "../hooks/useRecorder";
import { chrono } from "../lib/format";
import { ACTION, estMac as estMacLib } from "../lib/raccourcis";

interface Props { disabled: boolean; onEnvoyer: (texte: string) => void; onNotifier: (m: string) => void }

export default function Completer({ disabled, onEnvoyer, onNotifier }: Props) {
  const [ouvert, setOuvert] = useState(false);
  const [texte, setTexte] = useState("");
  const [transcription, setTranscription] = useState(false);
  const racine = useRef<HTMLDivElement>(null);
  const zone = useRef<HTMLTextAreaElement>(null);
  const bouton = useRef<HTMLButtonElement>(null);

  const apresEnregistrement = useCallback(async (blob: Blob) => {
    setTranscription(true);
    try {
      const t = await transcrire(blob);
      setTexte((x) => (x ? `${x} ${t}` : t).trim());
      zone.current?.focus();
    } catch {
      onNotifier("Transcription impossible. Vous pouvez taper le complément.");
    } finally {
      setTranscription(false);
    }
  }, [onNotifier]);
  const micro = useRecorder(apresEnregistrement, onNotifier);

  // Alt+M : ouvre le volet et démarre la dictée ; un second appui l'arrête (la transcription reste à relire avant envoi).
  const microRef = useRef(micro);
  microRef.current = micro;
  useEffect(() => {
    const f = (e: Event) => {
      if ((e as CustomEvent).detail !== "completer" || disabled) return;
      const m = microRef.current;
      setOuvert(true);
      if (m.etat === "enregistre") m.arreter();
      else if (m.etat === "repos") void m.demarrer();
    };
    window.addEventListener(ACTION, f);
    return () => window.removeEventListener(ACTION, f);
  }, [disabled]);

  useEffect(() => {
    if (!ouvert) return;
    const f = (e: MouseEvent) => { if (!racine.current?.contains(e.target as Node)) setOuvert(false); };
    document.addEventListener("mousedown", f);
    return () => document.removeEventListener("mousedown", f);
  }, [ouvert]);

  const fermer = useCallback(() => {
    micro.arreter(true);
    setOuvert(false);
    requestAnimationFrame(() => bouton.current?.focus());
  }, [micro]);

  const envoyer = () => {
    if (!texte.trim()) return;
    onEnvoyer(texte.trim());
    setTexte("");
    setOuvert(false);
    requestAnimationFrame(() => bouton.current?.focus());
  };

  return (
    <div ref={racine}>
      <button ref={bouton} type="button" className="btn" disabled={disabled} aria-expanded={ouvert} aria-haspopup="dialog" onClick={() => (ouvert ? fermer() : setOuvert(true))} aria-keyshortcuts="Alt+M">Compléter à la voix</button>
      {ouvert && (
        <PanneauCompleter zone={zone} texte={texte} setTexte={setTexte} micro={micro} transcription={transcription} onEnvoyer={envoyer} onFermer={fermer} />
      )}
    </div>
  );
}

type Micro = ReturnType<typeof useRecorder>;

function PanneauCompleter({ zone, texte, setTexte, micro, transcription, onEnvoyer, onFermer }: {
  zone: React.RefObject<HTMLTextAreaElement | null>; texte: string; setTexte: (t: string) => void; micro: Micro; transcription: boolean; onEnvoyer: () => void; onFermer: () => void;
}) {
  const panneau = useRef<HTMLDivElement>(null);
  useDialogue(panneau, onFermer, { rendreFocus: false });
  // Feuille (sheet) : voile + feuille centrée ; un clic hors de la feuille la ferme, comme Échap.
  return (
    <div className="modal" onMouseDown={(e) => { if (e.target === e.currentTarget) onFermer(); }}>
      <div ref={panneau} role="dialog" aria-modal="true" aria-labelledby="titre-completer" className="!w-[min(480px,100%)] p-6">
        <div className="flex items-baseline gap-3">
          <h2 id="titre-completer" className="titre-serif flex-1 text-[22px] leading-[1.2]">Compléter à la voix</h2>
          <button type="button" className="btn btn-ghost btn-sm" onClick={onFermer}>Fermer <span className="kbd">Échap</span></button>
        </div>
        <p className="mt-2 text-[15px] leading-snug text-[var(--mute)]">Dictez une précision (mesure oubliée, résultat manquant). Le reste du projet n'est pas modifié ; vous relisez avant d'intégrer.</p>
        <textarea ref={zone} value={texte} onChange={(e) => setTexte(e.target.value)} rows={4} aria-label="Complément de dictée"
          onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === "Enter") { e.preventDefault(); onEnvoyer(); } }}
          placeholder="Ex. PD-L1 à 60 % des cellules tumorales." className="champ mt-4 block w-full resize-none p-3 text-[16px] leading-[1.5]" />
        <div className="mt-4 flex items-center gap-3">
          <button type="button" className="btn" onClick={micro.basculer} disabled={transcription} aria-pressed={micro.etat === "enregistre"}>
            {micro.etat === "enregistre" ? <><span className="enregistrement-point" aria-hidden /> <span className="num">{chrono(micro.secondes)}</span> Arrêter</> : transcription ? "Transcription…" : "Dicter"}
          </button>
          <button type="button" className="btn btn-primary ml-auto" disabled={!texte.trim() || transcription} onClick={onEnvoyer}>Intégrer <span className="kbd">{estMacLib() ? "⌘↵" : "Ctrl+↵"}</span></button>
        </div>
      </div>
    </div>
  );
}
