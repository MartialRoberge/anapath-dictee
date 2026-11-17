import { describe, expect, it } from "vitest";
import { creerParseurSse, decoderEvenement, lireFluxSse, type SseMessage } from "./sse";
import type { ProjetEvent } from "../types";

const collecter = () => {
  const msgs: SseMessage[] = [];
  return { msgs, p: creerParseurSse((m) => msgs.push(m)) };
};

describe("parseur SSE", () => {
  it("parse event + data et ignore les commentaires", () => {
    const { msgs, p } = collecter();
    p.push(": keep-alive\n\nevent: step\ndata: {\"a\":1}\n\n");
    expect(msgs).toEqual([{ event: "step", data: '{"a":1}' }]);
  });
  it("tolère des chunks coupés au milieu d'une ligne et du CRLF", () => {
    const { msgs, p } = collecter();
    ["event: ste", "p\r\nda", "ta: {\"x\":", "2}\r", "\n\r\n", "event: partial\ndata: {}\n\n"].forEach((c) => p.push(c));
    expect(msgs.map((m) => m.event)).toEqual(["step", "partial"]);
    expect(msgs[0].data).toBe('{"x":2}');
  });
  it("joint les data multilignes et vide à la fin", () => {
    const { msgs, p } = collecter();
    p.push("data: a\ndata: b\n");
    p.flush();
    expect(msgs).toEqual([{ event: "message", data: "a\nb" }]);
  });
});

describe("décodage des évènements", () => {
  it("step valide avec valeurs par défaut", () => {
    const e = decoderEvenement({ event: "step", data: JSON.stringify({ id: "t1", titre: "x", statut: "ok", agent: "A", role: "extracteur" }) });
    expect(e?.event).toBe("step");
    expect(e && e.event === "step" && e.data.details).toEqual([]);
  });
  it("projet illisible -> erreur récupérable, autre évènement illisible -> ignoré", () => {
    expect(decoderEvenement({ event: "projet", data: "{pas du json" })).toMatchObject({ event: "error", data: { recuperable: true } });
    expect(decoderEvenement({ event: "step", data: "oops" })).toBeNull();
    expect(decoderEvenement({ event: "ping", data: "{}" })).toBeNull();
  });
  it("projet partiel normalisé sans rien inventer", () => {
    const e = decoderEvenement({ event: "projet", data: JSON.stringify({ id: "p", elements: [{ id: "e", texte: "t" }] }) });
    expect(e?.event === "projet" && e.data.elements[0].options).toEqual([]);
    expect(e?.event === "projet" && e.data.alertes).toEqual([]);
  });
});

describe("lireFluxSse", () => {
  it("lit un flux découpé en octets arbitraires", async () => {
    const enc = new TextEncoder();
    const texte = 'event: step\ndata: {"id":"a","titre":"t","statut":"en_cours"}\n\nevent: error\ndata: {"message":"boum","recuperable":false}\n\n';
    const octets = enc.encode(texte);
    const res = new Response(new ReadableStream({ start(c) { for (let i = 0; i < octets.length; i += 7) c.enqueue(octets.slice(i, i + 7)); c.close(); } }));
    const recus: ProjetEvent[] = [];
    await lireFluxSse(res, (e) => recus.push(e));
    expect(recus.map((e) => e.event)).toEqual(["step", "error"]);
    expect(recus[1]).toMatchObject({ data: { message: "boum", recuperable: false } });
  });
});
