"""Tests v0.3.0: flow diagram oficial, PRISMA-S, comandos new y check."""

from __future__ import annotations

from revisia.check import AdherenceReport, ItemAdherence, render_adherence_md
from revisia.config import ReviewProtocol
from revisia.exports import (
    PrismaCounts,
    render_flow_diagram,
    render_flow_markdown,
    render_flow_updated,
    render_methods,
    render_prisma_abstracts_checklist,
    render_prisma_s_checklist,
)
from revisia.exports.checklist import engine_search_date
from revisia.schemas.artifacts import SearchLog, SearchLogEntry

_COUNTS = PrismaCounts(
    identified=120,
    identified_by_source={"openalex": 40, "crossref": 40, "europepmc": 40},
    duplicates_removed=20,
    screened=100,
    excluded_ta=70,
    excluded_ta_human=10,
    excluded_ta_ai=60,
    fulltext_sought=30,
    fulltext_not_retrieved=8,
    fulltext_assessed=22,
    excluded_ft=5,
    excluded_ft_human=2,
    excluded_ft_ai=3,
    ft_exclusion_reasons={"población incorrecta": 3, "sin datos de desenlace": 2},
    included=17,
)


def test_flow_diagram_plantilla_oficial_v1() -> None:
    mermaid = render_flow_diagram(_COUNTS)
    # Cajas oficiales de la plantilla v1
    assert "Registros identificados (n = 120)" in mermaid
    assert "openalex (n = 40)" in mermaid
    assert "Duplicados (n = 20)" in mermaid
    assert "Marcados inelegibles por automatización (n = 0)" in mermaid
    assert "Registros cribados (n = 100)" in mermaid
    # Nota ** de la plantilla oficial: separación humano vs IA (trAIce R1)
    assert "por humano (n = 10) · por IA (n = 60)**" in mermaid
    assert "Informes evaluados para elegibilidad (n = 22)" in mermaid
    # Razones de exclusión (cajas Reason 1..n)
    assert "población incorrecta (n = 3)" in mermaid
    assert "sin datos de desenlace (n = 2)" in mermaid
    assert "Estudios incluidos en la revisión (n = 17)" in mermaid
    assert "BMJ 2021;372:n71" in mermaid  # atribución CC BY 4.0


def test_flow_diagram_buscados_no_recuperados_evaluados() -> None:
    # PRISMA estricto (D2; auditoría 2026-09-03, M11): los no recuperados tienen
    # su caja y no cuentan como evaluados.
    mermaid = render_flow_diagram(_COUNTS)
    assert 'S["Informes buscados para recuperación (n = 30)"]' in mermaid
    assert 'N["Informes no recuperados (n = 8)"]' in mermaid
    assert 'E["Informes evaluados para elegibilidad (n = 22)"]' in mermaid
    for arista in ("C --> S", "S --> N", "S --> E", "E --> F"):
        assert arista in mermaid
    assert "Informes excluidos (n = 5)<br/>por humano (n = 2) · por IA (n = 3)**" in mermaid
    assert "rescatados por el revisor" not in mermaid
    assert "sin texto completo recuperable" not in mermaid  # caja retirada

    con_rescate = _COUNTS.model_copy(
        update={"fulltext_not_retrieved": 6, "fulltext_rescued": 2, "fulltext_assessed": 24}
    )
    mermaid = render_flow_diagram(con_rescate)
    assert "(rescatados por el revisor: n = 2)***" in mermaid
    assert "\\*** Informes que el motor no pudo recuperar" in mermaid

    table = render_flow_markdown(_COUNTS)
    assert "| Informes buscados para recuperación | 30 |" in table
    assert "| Informes no recuperados | 8 |" in table
    assert "| Informes evaluados para elegibilidad | 22 |" in table
    assert "| — excluidos por humano (elegibilidad) | 2 |" in table
    assert "| — excluidos por IA (elegibilidad) | 3 |" in table
    assert "| — rescatados por el revisor | 2 |" in render_flow_markdown(con_rescate)


def test_flow_markdown_desglosa_todo() -> None:
    table = render_flow_markdown(_COUNTS)
    assert "— identificados en openalex | 40" in table
    assert "— excluidos por IA | 60" in table
    assert "— razón: población incorrecta | 3" in table


def test_flow_updated_living_review() -> None:
    mermaid = render_flow_updated(
        _COUNTS, previous_included=27, new_included=4, dropped_from_previous=2
    )
    assert "versión anterior (n = 27)" in mermaid
    assert "Estudios nuevos incluidos (n = 4)" in mermaid
    assert "Total de estudios incluidos en la revisión (n = 29)" in mermaid  # 27-2+4
    assert "Retirados de la versión anterior (n = 2)" in mermaid


def test_checklist_prisma_s_prerellena() -> None:
    markdown = render_prisma_s_checklist(
        databases=["OpenAlex", "Europe PMC"],
        search_window={"from": "2015-01-01", "to": "2026-12-31", "executed": "2026-07-05"},
        counts=_COUNTS,
    )
    assert markdown.count("- [ ]") == 16
    assert "s13643-020-01542-z" in markdown  # cita PRISMA-S
    assert "OpenAlex, Europe PMC" in markdown
    assert "Búsqueda ejecutada: 2026-07-05" in markdown
    assert "Total identificados: 120" in markdown
    assert "20 duplicados eliminados" in markdown


def test_render_adherencia_completa_27_filas() -> None:
    report = AdherenceReport(
        items=[
            ItemAdherence(item=1, status="cubierto", evidence="'revisión sistemática' en título"),
            ItemAdherence(item=16, status="parcial", evidence="flujo sin razones de exclusión"),
        ]
    )
    markdown = render_adherence_md(report, source_name="doc.md", model="fake:fake-1")
    assert markdown.count("| ") > 27  # tabla con las 27 filas
    assert "✅ cubierto" in markdown
    assert "🟡 parcial" in markdown
    assert "⬜ sin_evaluar" in markdown  # los 25 no evaluados aparecen igual
    assert "✅ cubiertos 1 · 🟡 parciales 1 · ❌ ausentes 0" in markdown


def test_cli_new_scaffold(tmp_path, capsys, monkeypatch) -> None:
    import shutil

    from revisia.cli import main

    # plantilla mínima
    template = tmp_path / "protocols" / "_TEMPLATE"
    template.mkdir(parents=True)
    (template / "protocol.yml").write_text(
        'title: "Plantilla · Revisión Sistemática PRISMA 2020"\n', encoding="utf-8"
    )
    (template / "protocolo-prisma-p.md").write_text("# PRISMA-P\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main(["new", "mi-revision"]) == 0
    dest = tmp_path / "protocols" / "mi-revision"
    assert (dest / "protocolo-prisma-p.md").exists()
    proto = (dest / "protocol.yml").read_text(encoding="utf-8")
    assert "mi-revision · Revisión Sistemática PRISMA 2020" in proto

    # rechaza sobrescribir
    assert main(["new", "mi-revision"]) == 2
    shutil.rmtree(dest)


def test_cli_check_con_fake(tmp_path, capsys) -> None:
    from revisia.cli import main

    manuscript = tmp_path / "manuscrito.md"
    manuscript.write_text(
        "# Revisión sistemática de ejemplo\n\nMétodos: buscamos en OpenAlex.\n",
        encoding="utf-8",
    )
    assert main(["check", str(manuscript), "--provider", "fake", "--model", "fake-1"]) == 0
    out = manuscript.with_suffix(".prisma-check.md")
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "Pre-chequeo de adherencia PRISMA 2020" in content
    printed = capsys.readouterr().out
    assert "no sustituye la revisión editorial humana" in printed


def test_prisma_s_desde_el_log_de_busqueda() -> None:
    # M12: los ítems 8 y 13 decían lo declarado, no lo ejecutado.
    hora = "2026-10-04T10:00:00+00:00"
    log = SearchLog(
        started_utc=hora,
        finished_utc=hora,
        max_results=50,
        mailto_set=False,
        entries=[
            SearchLogEntry(
                database="OpenAlex",
                db_key="openalex",
                kind="database",
                declared=True,
                status="ok",
                query="cadena openalex",
                query_origin="file",
                query_file="00_protocol/search_strings/openalex.txt",
                started_utc=hora,
            ),
            SearchLogEntry(
                database="Europe PMC",
                db_key="europepmc",
                kind="database",
                declared=True,
                status="ok",
                query="la pregunta",
                query_origin="question_fallback",
                started_utc=hora,
            ),
            SearchLogEntry(
                database="Scopus",
                db_key="scopus",
                kind="database",
                declared=True,
                status="manual_only",
            ),
        ],
    )
    ventana = {"from": "2015-01-01", "to": "2026-12-31", "executed": "2026-06-26"}
    markdown = render_prisma_s_checklist(
        databases=["OpenAlex", "Europe PMC", "Scopus"], search_window=ventana, search_log=log
    )
    assert markdown.count("- [ ]") == 16
    item_8 = next(x for x in markdown.splitlines() if x.startswith("- [ ] 8."))
    assert "OpenAlex: «cadena openalex» (00_protocol/search_strings/openalex.txt)" in item_8
    assert "Europe PMC: ⚠ sin cadena propia, se usó la pregunta «la pregunta»" in item_8
    assert "Scopus: importación manual" in item_8
    item_13 = next(x for x in markdown.splitlines() if x.startswith("- [ ] 13."))
    assert "fecha del motor): 2026-10-04" in item_13
    assert "Difiere de search_window.executed (2026-06-26)" in item_13

    resumenes = render_prisma_abstracts_checklist(
        databases=["OpenAlex"], search_window=ventana, search_log=log
    )
    assert "última búsqueda: 2026-10-04 (registrada por el motor)" in resumenes
    protocolo = ReviewProtocol.model_validate(
        {"slug": "d", "title": "D", "question": {"text": "¿X?", "framework": "PEO"}}
    )
    metodos = render_methods(protocol=protocolo, counts=_COUNTS, search_log=log)
    assert "fecha registrada por el motor): 2026-10-04" in metodos
    assert "00_protocol/search_strings/" in metodos
    assert "Sin cadena propia en Europe PMC" in metodos


_HORA = "2026-10-04T10:00:00+00:00"


def _entrada(**campos) -> SearchLogEntry:
    """Entrada del log de búsqueda con los valores por omisión de una base ejecutada."""
    base = {
        "database": "OpenAlex",
        "db_key": "openalex",
        "kind": "database",
        "declared": True,
        "status": "ok",
        "backend": "openalex.search_openalex",
        "started_utc": _HORA,
    }
    return SearchLogEntry(**{**base, **campos})


def _log(*entradas: SearchLogEntry) -> SearchLog:
    return SearchLog(
        started_utc=_HORA, finished_utc=_HORA, max_results=50, mailto_set=False, entries=entradas
    )


def _item(markdown: str, numero: int) -> str:
    return next(x for x in markdown.splitlines() if x.startswith(f"- [ ] {numero}."))


def test_prisma_s_cadena_multilinea_es_una_sola_linea() -> None:
    # Una cadena PubMed/Scopus de varias líneas partía el ítem 8 y, al pasar a HTML
    # (Anexo E), una línea con «#» se volvía <h1> y otra con «- » una lista.
    cadena = "#1 salud\n#2 educación\n- otro\n#1 AND #2"
    log = _log(
        _entrada(query=cadena, query_origin="file", query_file="00_protocol/search_strings/o.txt"),
        _entrada(
            database="Europe PMC",
            db_key="europepmc",
            query="  ¿qué\n# pasa?  ",
            query_origin="question_fallback",
        ),
    )
    markdown = render_prisma_s_checklist(search_log=log)
    assert "#1 salud #2 educación - otro #1 AND #2" in _item(markdown, 8)
    assert "«¿qué # pasa?»" in _item(markdown, 8)
    # Ninguna línea del Markdown arranca como encabezado ni como lista por culpa de la cadena.
    assert not [x for x in markdown.splitlines() if x.startswith(("#2", "- otro", "#1 AND"))]
    assert markdown.count("- [ ]") == 16


def test_prisma_s_base_fallida_no_se_muestra_como_ejecutada() -> None:
    error = "ReadTimeout: " + "x" * 300
    log = _log(
        _entrada(query="llm", query_origin="file", status="failed", error=error),
        _entrada(database="Crossref", db_key="crossref", query="ml", query_origin="file"),
    )
    markdown = render_prisma_s_checklist(search_log=log)
    item_8, item_13 = _item(markdown, 8), _item(markdown, 13)
    assert "OpenAlex: «llm»" in item_8
    assert "(falló: ReadTimeout: " in item_8
    assert "(falló: ReadTimeout: " in item_13
    assert "OpenAlex 2026-10-04 (falló:" in item_13
    assert "x" * 200 not in item_8  # el error se recorta (~120 caracteres)
    assert "Crossref: «ml»" in item_8
    assert "Crossref 2026-10-04" in item_13
    assert "Crossref 2026-10-04 (falló" not in item_13


def test_engine_search_date_ignora_las_importaciones() -> None:
    # Una importación lleva la hora de lectura del fichero, no la de la búsqueda externa.
    importada = _entrada(
        database="imported/scopus.ris",
        db_key="imported",
        kind="manual_import",
        backend=None,
        started_utc="2026-09-01T08:00:00+00:00",
    )
    assert engine_search_date(_log(_entrada(), importada)) == "2026-10-04"
    inyectada = _entrada(
        database="search_fn",
        db_key="search_fn",
        kind="injected",
        backend=None,
        started_utc="2026-10-02T08:00:00+00:00",
    )
    assert engine_search_date(_log(_entrada(), importada, inyectada)) == "2026-10-02"
    # Sin búsquedas del motor se queda el inicio del log, como antes.
    assert engine_search_date(_log(importada)) == "2026-10-04"


def test_prisma_s_manual_only_y_importaciones_se_rotulan_aparte() -> None:
    log = _log(
        _entrada(),
        _entrada(
            database="Scopus",
            db_key="scopus",
            status="manual_only",
            backend=None,
            started_utc=None,
            query="TITLE-ABS-KEY(llm)",
            query_origin="file",
            query_file="00_protocol/search_strings/scopus.txt",
        ),
        _entrada(
            database="imported/scopus.ris",
            db_key="imported",
            kind="manual_import",
            backend=None,
            started_utc="2026-09-01T08:00:00+00:00",
        ),
    )
    markdown = render_prisma_s_checklist(search_log=log)
    item_8, item_13 = _item(markdown, 8), _item(markdown, 13)
    assert "Scopus: cadena declarada para una búsqueda externa (importada vía imported/)" in item_8
    assert "«TITLE-ABS-KEY(llm)»" in item_8
    assert "Scopus: «TITLE-ABS-KEY(llm)» (" not in item_8  # no es una cadena «ejecutada»
    assert "imported/scopus.ris importado el 2026-09-01" in item_13
    assert "imported/scopus.ris 2026-09-01" not in item_13
    assert "(fecha del motor): 2026-10-04" in item_13


def test_prisma_s_ramas_unknown_e_injected_y_fechas_coincidentes() -> None:
    log = _log(
        _entrada(
            database="Atlantis",
            db_key="atlantis",
            status="unknown",
            backend=None,
            started_utc=None,
        ),
        _entrada(database="search_fn", db_key="search_fn", kind="injected", backend=None),
    )
    markdown = render_prisma_s_checklist(search_window={"executed": "2026-10-04"}, search_log=log)
    item_8, item_13 = _item(markdown, 8), _item(markdown, 13)
    assert "Atlantis: base desconocida, sin búsqueda" in item_8
    assert "búsqueda inyectada (search_fn): sin cadena por base" in item_8
    assert "(fecha del motor): 2026-10-04" in item_13
    assert "⚠" not in item_13  # fechas coincidentes: sin aviso
    assert "Difiere" not in item_13


def test_resumenes_item_4_con_el_log_aunque_no_haya_bases_declaradas() -> None:
    # Sin `databases:` el motor busca en OpenAlex por defecto y lo deja en el log.
    log = _log(_entrada(declared=False, query="llm", query_origin="question_fallback"))
    markdown = render_prisma_abstracts_checklist(search_log=log)
    item_4 = next(x for x in markdown.splitlines() if x.startswith("- [ ] 4."))
    assert "Bases: OpenAlex" in item_4
    assert "última búsqueda: 2026-10-04 (registrada por el motor)" in item_4
    assert "(completar)" not in item_4
    # Sin log ni bases no hay evidencia, como antes.
    sin_nada = render_prisma_abstracts_checklist()
    assert "(completar)" in next(x for x in sin_nada.splitlines() if x.startswith("- [ ] 4."))


def test_metodos_cita_search_strings_solo_si_se_usaron_cadenas_por_base() -> None:
    protocolo = ReviewProtocol.model_validate(
        {"slug": "d", "title": "D", "question": {"text": "¿X?", "framework": "PEO"}}
    )
    con_fichero = _log(_entrada(query="llm", query_origin="file", query_file="x.txt"))
    solo_pregunta = _log(_entrada(query="¿X?", query_origin="question_fallback"))
    inyectada = _log(_entrada(database="search_fn", kind="injected", backend=None))
    assert "00_protocol/search_strings/" in render_methods(
        protocol=protocolo, counts=_COUNTS, search_log=con_fichero
    )
    for log in (solo_pregunta, inyectada):
        assert "00_protocol/search_strings/" not in render_methods(
            protocol=protocolo, counts=_COUNTS, search_log=log
        )
    # Sin log no se sabe qué se usó: se conserva la cita de siempre.
    assert "00_protocol/search_strings/" in render_methods(protocol=protocolo, counts=_COUNTS)
