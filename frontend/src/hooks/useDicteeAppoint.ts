/**
 * La dictee d'appoint : ajouter une precision a la voix, sans redicter le tout.
 *
 * Distincte de la dictee INITIALE, qui produit le compte rendu. Celle-ci
 * complete un compte rendu deja redige — une mesure oubliee, un resultat qui
 * arrive, une precision. Les deux passent par la meme transcription, mais elles
 * n'ont ni le meme moment ni le meme geste, et les confondre dans un seul
 * panneau etait ce qui rendait l'ajout impraticable.
 *
 * L'API est volontairement en DEUX temps — demarrer, puis arreter et rendre le
 * texte. Un unique `dicter(): Promise<string>` qui demarre et resout "quand
 * c'est fini" n'offre aucun moyen de dire que c'est fini : on demarrait une
 * dictee qu'on ne pouvait plus arreter.
 */

import { useCallback, useRef, useState } from "react";
import { transcribeAudio } from "@/services/api";

/** Le format le plus largement accepte par les navigateurs, dans l'ordre. */
const FORMATS: readonly string[] = ["audio/webm", "audio/mp4", "audio/ogg"];

function extensionDe(mimeType: string): string {
  if (mimeType.includes("mp4")) return "m4a";
  if (mimeType.includes("ogg")) return "ogg";
  return "webm";
}

export interface DicteeAppoint {
  enCours: boolean;
  demarrer: () => Promise<void>;
  arreter: () => Promise<string>;
}

export function useDicteeAppoint(): DicteeAppoint {
  const [enCours, setEnCours] = useState(false);
  const enregistreurRef = useRef<MediaRecorder | null>(null);
  const morceauxRef = useRef<Blob[]>([]);
  const fluxRef = useRef<MediaStream | null>(null);

  /** Coupe le micro. Sans cela, la pastille d'enregistrement du navigateur
   *  reste allumee apres la dictee : le praticien croit etre encore ecoute. */
  const libererMicro = useCallback(() => {
    fluxRef.current?.getTracks().forEach((piste) => piste.stop());
    fluxRef.current = null;
  }, []);

  const demarrer = useCallback(async () => {
    const flux = await navigator.mediaDevices.getUserMedia({ audio: true });
    fluxRef.current = flux;

    const format = FORMATS.find((f) => MediaRecorder.isTypeSupported(f));
    const enregistreur = new MediaRecorder(
      flux,
      format ? { mimeType: format } : {},
    );
    morceauxRef.current = [];
    enregistreur.ondataavailable = (evenement) => {
      if (evenement.data.size > 0) morceauxRef.current.push(evenement.data);
    };
    enregistreur.start();
    enregistreurRef.current = enregistreur;
    setEnCours(true);
  }, []);

  const arreter = useCallback(async (): Promise<string> => {
    const enregistreur = enregistreurRef.current;
    if (enregistreur === null) return "";

    const morceaux = await new Promise<Blob[]>((resoudre) => {
      enregistreur.onstop = () => resoudre(morceauxRef.current);
      enregistreur.stop();
    });
    enregistreurRef.current = null;
    setEnCours(false);
    libererMicro();

    const type = enregistreur.mimeType || "audio/webm";
    const audio = new Blob(morceaux, { type });
    // Un enregistrement vide n'est pas une erreur : le praticien a pu cliquer
    // deux fois. On rend une chaine vide, la barre n'insere rien.
    if (audio.size === 0) return "";

    return await transcribeAudio(audio, `appoint.${extensionDe(type)}`);
  }, [libererMicro]);

  return { enCours, demarrer, arreter };
}
