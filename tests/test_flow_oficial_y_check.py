"""Tests v0.3.0: flow diagram oficial, PRISMA-S, comandos new y check."""

from __future__ import annotations

from revisia.check import AdherenceReport, ItemAdherence, render_adherence_md
from revisia.exports import (
    PrismaCounts,
    render_flow_diagram,
    render_flow_markdown,
    render_flow_updated,
    render_prisma_s_checklist,
)

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
