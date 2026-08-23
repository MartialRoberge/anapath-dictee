import { useState, useEffect, useCallback } from "react";
import {
  ArrowLeft,
  RefreshCw,
  BarChart3,
  FolderOpen,
  AlertTriangle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { API_BASE } from "@/lib/config";
import SyntheseEtude from "../components/etude-admin/SyntheseEtude";
import type { DonneesSynthese } from "../components/etude-admin/SyntheseEtude";
import ListeDossiersEtude from "../components/etude-admin/ListeDossiersEtude";
import type { LigneDossierEtude } from "../components/etude-admin/ListeDossiersEtude";
import DetailDossierEtude from "../components/etude-admin/DetailDossierEtude";
import type { DossierDetailleEtude } from "../components/etude-admin/DetailDossierEtude";

type Onglet = "synthese" | "dossiers";

interface EtudeAdminPageProps {
  /** Jeton fourni par le point d'assemblage, comme pour AdminPage : cette page
   *  ne duplique aucune gestion de session. */
  token: string | null;
  onBack: () => void;
}

/* ------------------------------------------------------------------ */
/*  Acces aux vues d'administration de l'etude                         */
/* ------------------------------------------------------------------ */

async function lireEtude<T>(chemin: string, token: string): Promise<T> {
  const reponse = await fetch(`${API_BASE}/admin/etude${chemin}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!reponse.ok) {
    const corps = (await reponse.json().catch(() => null)) as {
      detail?: string;
    } | null;
    throw new Error(corps?.detail ?? `Erreur HTTP ${reponse.status}`);
  }
  return reponse.json() as Promise<T>;
}

function messageErreur(erreur: unknown): string {
  return erreur instanceof Error ? erreur.message : "Erreur inconnue";
}

/* ------------------------------------------------------------------ */
/*  Etats partages                                                     */
/* ------------------------------------------------------------------ */

function Chargement() {
  return (
    <div className="flex items-center justify-center py-20 text-muted-foreground">
      <div className="h-5 w-5 animate-spin rounded-full border-2 border-muted border-t-primary" />
    </div>
  );
}

function MessageErreur({
  message,
  onReessayer,
}: {
  message: string;
  onReessayer: () => void;
}) {
  return (
    <div className="flex flex-col items-start gap-3 rounded-lg border border-destructive/20 bg-destructive/5 p-4 sm:flex-row sm:items-center">
      <AlertTriangle className="h-4 w-4 shrink-0 text-destructive" />
      <p className="min-w-0 flex-1 break-words text-sm text-muted-foreground">
        {message}
      </p>
      <Button variant="outline" size="sm" onClick={onReessayer}>
        <RefreshCw className="h-3.5 w-3.5" />
        Reessayer
      </Button>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  EtudeAdminPage                                                     */
/* ------------------------------------------------------------------ */

export default function EtudeAdminPage({
  token,
  onBack,
}: EtudeAdminPageProps) {
  const [onglet, setOnglet] = useState<Onglet>("synthese");
  const [synthese, setSynthese] = useState<DonneesSynthese | null>(null);
  const [dossiers, setDossiers] = useState<LigneDossierEtude[]>([]);
  const [chargement, setChargement] = useState(true);
  const [erreur, setErreur] = useState<string | null>(null);

  const [dossierId, setDossierId] = useState<string | null>(null);
  const [detail, setDetail] = useState<DossierDetailleEtude | null>(null);
  const [detailChargement, setDetailChargement] = useState(false);
  const [detailErreur, setDetailErreur] = useState<string | null>(null);
  /** Rejouer le meme cas apres un echec : re-selectionner le meme identifiant
   *  ne relancerait rien, React ne renotifie pas un etat inchange. */
  const [tentative, setTentative] = useState(0);

  const charger = useCallback(async () => {
    if (!token) {
      setErreur("Authentification requise pour consulter l'etude.");
      setChargement(false);
      return;
    }
    setChargement(true);
    setErreur(null);
    try {
      const [vueSynthese, vueDossiers] = await Promise.all([
        lireEtude<DonneesSynthese>("/synthese", token),
        lireEtude<LigneDossierEtude[]>("/dossiers", token),
      ]);
      setSynthese(vueSynthese);
      setDossiers(vueDossiers);
    } catch (echec: unknown) {
      setErreur(messageErreur(echec));
    } finally {
      setChargement(false);
    }
  }, [token]);

  useEffect(() => {
    charger();
  }, [charger]);

  // Le detail suit la selection. Le drapeau `obsolete` protege du cas ou une
  // reponse lente arrive apres qu'un autre cas a ete ouvert.
  useEffect(() => {
    if (!token || dossierId === null) {
      setDetail(null);
      return;
    }
    let obsolete = false;
    setDetailErreur(null);
    setDetailChargement(true);
    lireEtude<DossierDetailleEtude>(`/dossiers/${dossierId}`, token)
      .then((vue) => {
        if (!obsolete) setDetail(vue);
      })
      .catch((echec: unknown) => {
        if (!obsolete) setDetailErreur(messageErreur(echec));
      })
      .finally(() => {
        if (!obsolete) setDetailChargement(false);
      });
    return () => {
      obsolete = true;
    };
  }, [dossierId, token, tentative]);

  return (
    <div className="flex h-screen flex-col bg-background text-foreground">
      <header className="flex h-12 shrink-0 items-center gap-3 border-b px-5">
        <Button variant="ghost" size="icon" onClick={onBack}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <h1 className="truncate text-base font-bold">Etude MARC</h1>
        <Button
          variant="ghost"
          size="icon"
          onClick={charger}
          className="ml-auto"
          title="Actualiser"
        >
          <RefreshCw className={cn("h-4 w-4", chargement && "animate-spin")} />
        </Button>
      </header>

      {/* Onglets */}
      <div className="flex border-b">
        {(
          [
            { key: "synthese", label: "Synthese", icon: BarChart3 },
            { key: "dossiers", label: "Cas", icon: FolderOpen },
          ] as const
        ).map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            type="button"
            onClick={() => setOnglet(key)}
            className={cn(
              "flex items-center gap-2 px-4 py-3 text-sm font-medium transition-colors sm:px-5",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
              onglet === key
                ? "border-b-2 border-primary text-primary"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Icon className="h-4 w-4" />
            {label}
          </button>
        ))}
      </div>

      <main className="flex-1 overflow-y-auto p-4 sm:p-5">
        {/* Plus large que les autres vues admin : les deux lectures d'un taux,
            puis la liste et la comparaison propose/valide, n'ont d'interet que
            cote a cote. */}
        <div
          className={cn(
            "mx-auto w-full",
            onglet === "synthese" ? "max-w-5xl" : "max-w-7xl",
          )}
        >
          {erreur ? (
            <MessageErreur message={erreur} onReessayer={charger} />
          ) : chargement && synthese === null ? (
            <Chargement />
          ) : onglet === "synthese" ? (
            synthese && <SyntheseEtude synthese={synthese} />
          ) : (
            <div className="grid gap-4 xl:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
              {/* Sous xl, la liste laisse la place au cas ouvert. Tant qu'il
                  n'y a rien a lister, elle occupe toute la largeur : un cadre
                  d'attente a cote d'un vide n'apprend rien. */}
              <div
                className={cn(
                  "min-w-0",
                  // La liste reste sous les yeux pendant la lecture d'un cas :
                  // c'est ce qui permet d'enchainer les dossiers sans revenir
                  // en arriere.
                  "xl:sticky xl:top-0 xl:max-h-[calc(100vh-8rem)] xl:self-start xl:overflow-y-auto xl:pr-1 scrollbar-thin",
                  dossierId !== null && "hidden xl:block",
                  dossiers.length === 0 && "xl:col-span-2",
                )}
              >
                <ListeDossiersEtude
                  dossiers={dossiers}
                  dossierSelectionne={dossierId}
                  onSelectionner={setDossierId}
                />
              </div>

              {dossierId === null ? (
                dossiers.length > 0 && (
                  <div className="hidden min-h-[18rem] items-center justify-center rounded-xl border border-dashed p-10 text-center text-sm text-muted-foreground xl:flex">
                    Ouvrez un cas pour remonter d'un taux jusqu'a la phrase de
                    dictee en cause.
                  </div>
                )
              ) : (
                <div className="min-w-0">
                  {detailErreur ? (
                    <MessageErreur
                      message={detailErreur}
                      onReessayer={() => setTentative((n) => n + 1)}
                    />
                  ) : detailChargement || detail === null ? (
                    <Chargement />
                  ) : (
                    <DetailDossierEtude
                      dossier={detail}
                      onFermer={() => setDossierId(null)}
                    />
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
