import { useState, useCallback } from "react";
import RecorderPanel from "./components/RecorderPanel";
import ReportPanel from "./components/ReportPanel";
import { formatTranscription } from "./services/api";
import type { DonneeManquante } from "./services/api";
import "./App.css";

export default function App() {
  const [rawTranscription, setRawTranscription] = useState<string | null>(null);
  const [report, setReport] = useState<string | null>(null);
  const [donneesManquantes, setDonneesManquantes] = useState<DonneeManquante[]>([]);
  const [organeDetecte, setOrganeDetecte] = useState<string>("");
  const [reformatting, setReformatting] = useState(false);

  const handleReset = () => {
    setRawTranscription(null);
    setReport(null);
    setDonneesManquantes([]);
    setOrganeDetecte("");
  };

  const handleFormatted = (
    newReport: string,
    organe: string,
    manquantes: DonneeManquante[]
  ) => {
    setReport(newReport);
    setOrganeDetecte(organe);
    setDonneesManquantes(manquantes);
  };

  const handleReformat = useCallback(
    async (text: string) => {
      if (!text.trim() || reformatting) return;
      setReformatting(true);
      try {
        const result = await formatTranscription(text, report ?? undefined);
        setReport(result.formatted_report);
        setOrganeDetecte(result.organe_detecte);
        setDonneesManquantes(result.donnees_manquantes);
      } catch {
        alert("Erreur lors de la mise en forme.");
      } finally {
        setReformatting(false);
      }
    },
    [reformatting, report]
  );

  return (
    <div className="app-container">
      <header className="app-header">
        <h1>Demo</h1>
        <span className="app-subtitle">Dictee anatomopathologique</span>
      </header>
      <main className="app-main">
        <section className="panel panel-left">
          <RecorderPanel
            rawTranscription={rawTranscription}
            report={report}
            onTranscription={setRawTranscription}
            onFormatted={handleFormatted}
            onReset={handleReset}
            onRawChange={setRawTranscription}
            onReformat={handleReformat}
            reformatting={reformatting}
          />
        </section>
        <section className="panel panel-right">
          <ReportPanel
            report={report}
            onReportChange={setReport}
            donneesManquantes={donneesManquantes}
            organeDetecte={organeDetecte}
          />
        </section>
      </main>
    </div>
  );
}
