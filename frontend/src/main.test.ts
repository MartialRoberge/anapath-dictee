import { readFileSync, existsSync } from "node:fs";
import { describe, expect, it } from "vitest";

const lire = (p: string) => readFileSync(new URL(p, import.meta.url), "utf8");

describe("ancienne application retirée", () => {
  it("main.tsx monte toujours la v3, sans montage ?legacy=1", () => {
    const main = lire("./main.tsx");
    expect(main).toContain('import("./v3/V3App")');
    expect(main).not.toMatch(/legacy/i);
    expect(main).not.toContain('import("./App")');
  });
  it("les fichiers de l'ancienne app n'existent plus", () => {
    for (const f of ["./App.tsx", "./pages/AdminPage.tsx", "./pages/LoginPage.tsx", "./services/api.ts", "./components/ReportPanel.tsx", "./components/Toast.tsx"]) {
      expect(existsSync(new URL(f, import.meta.url)), f).toBe(false);
    }
  });
  it("aucun lien vers l'ancienne version dans la v3", () => {
    expect(lire("./v3/components/Sidebar.tsx")).not.toContain("legacy");
    expect(lire("./v3/admin/AdminV3.tsx")).not.toContain("legacy");
    expect(lire("../index.html")).not.toContain("legacy");
  });
});
