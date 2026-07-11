"""Tests du moteur local (avec fournisseur LLM factice) — génération automatique."""


async def test_generate_injects_organ_context_and_returns_report(local_engine_factory):
    payload = {
        "cr": "**__BIOPSIE PULMONAIRE__**\n**Microscopie :**\nADK.\n"
        "**__CONCLUSION :__**\n**Adenocarcinome infiltrant.**",
        "organe": "poumon",
        "type_prelevement": "biopsie",
        "alertes": [
            {"champ": "phenotype IHC", "description": "preciser TTF1",
             "section": "ihc", "raison": "adk pulmonaire"}
        ],
    }
    engine, provider = local_engine_factory(payload)
    r = await engine.generate("biopsie pulmonaire, carotte, adenocarcinome TTF1")

    assert "poumon" in r.organes_detectes
    assert r.organe == "poumon"
    assert r.provider == "fake"
    assert [a.champ for a in r.alertes] == ["phenotype IHC"]
    # Le contexte métier auto-détecté a bien été injecté dans le prompt système.
    assert "CONTEXTE METIER" in provider.calls[0].system
    assert provider.calls[0].json_object is True


async def test_generate_no_template_choice_needed(local_engine_factory):
    # Aucune notion de template à choisir : la signature n'accepte pas de template.
    payload = {"cr": "**Micro :** x\n**__CONCLUSION :__**\n**x**",
               "organe": "sein", "type_prelevement": "biopsie", "alertes": []}
    engine, provider = local_engine_factory(payload)
    r = await engine.generate("biopsie du sein, carcinome canalaire, grade SBR II")
    assert "sein" in r.organes_detectes
    assert "Sein" in provider.calls[0].system  # connaissances sein injectées


async def test_generate_multi_organ(local_engine_factory):
    payload = {"cr": "**Micro :** x\n**__CONCLUSION :__**\n**x**",
               "organe": "estomac", "type_prelevement": "biopsie", "alertes": []}
    engine, provider = local_engine_factory(payload)
    r = await engine.generate("biopsies etagees oesophage bas et estomac antre")
    assert "estomac" in r.organes_detectes and "oesophage" in r.organes_detectes
    assert "PLUSIEURS ORGANES" in provider.calls[0].system


async def test_generate_number_guard_end_to_end(local_engine_factory):
    payload = {
        "cr": "**Macroscopie :**\nLesion de 99 mm.\n**__CONCLUSION :__**\n**ADK.**",
        "organe": "poumon", "type_prelevement": "piece_operatoire", "alertes": [],
    }
    engine, _ = local_engine_factory(payload)
    r = await engine.generate("piece pulmonaire adenocarcinome sans taille")
    assert any("99" in w for w in r.warnings)


async def test_generate_truncated_raises(local_engine_factory):
    payload = {"cr": "x", "organe": "poumon", "type_prelevement": "biopsie"}
    engine, _ = local_engine_factory(payload, truncated=True)
    try:
        await engine.generate("biopsie")
        assert False, "devrait lever"
    except ValueError as exc:
        assert "tronque" in str(exc)


async def test_iterate_merges_sources_for_number_guard(local_engine_factory):
    payload = {
        "cr": "**Macroscopie :**\nLesion de 18 mm.\n**__CONCLUSION :__**\n**ADK.**",
        "organe": "poumon", "type_prelevement": "piece_operatoire", "alertes": [],
    }
    engine, _ = local_engine_factory(payload)
    r = await engine.iterate(
        rapport_actuel="Lesion de 18 mm decrite precedemment.",
        nouveau_transcript="on ajoute que ALK est negatif",
    )
    assert not any("18" in w for w in r.warnings)
