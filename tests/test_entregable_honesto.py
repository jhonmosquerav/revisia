"""``metodologia.md`` y los checklists dicen lo que pasó (revisión final de la Ola 1, grupo D).

Lo que el producto escribe para un lector no afirma algo que el código no hace: el
meta-análisis sale de ``effects.yml`` y no de la extracción (D1), la fecha tecleada en el
protocolo no es la registrada (D2), con ``--auto-approve`` el reporte no queda «pendiente» de
nadie (D3), «rescate» tiene un solo significado (D4) y los detalles de D5 (autonomía repetida,
«ensemble» de un solo modelo, bases manuales llamadas «APIs abiertas», rutas y fechas).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fakes import ScriptedProvider, fetch_disponible

from revisia.audit import checks_search
from revisia.config import ReviewProtocol, load_protocol
from revisia.exclusions import ExclusionBreakdown
from revisia.exports import (
    PrismaCounts,
    render_methods,
    render_prisma_2020_checklist,
    render_prisma_s_checklist,
    render_traice_checklist,
)
from revisia.exports import checklist as checklist_mod
from revisia.meta_analysis import meta_analyze
from revisia.orchestration import pipeline as pipeline_mod
from revisia.orchestration.pipeline import run_pipeline
from revisia.orchestration.run_context import RunContext
from revisia.protocol_files import load_protocol_files
from revisia.schemas.artifacts import SearchLog, SearchLogEntry
from revisia.schemas.records import SearchRecord

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "demo-mini-review"
_HORA = "2026-10-04T10:00:00+00:00"
_EFECTIVA = {
    "screening_ta": "A1",
    "screening_ft": "A0",
    "extraccion": "A0",
    "rob": "A0",
    "reporte": "A1",
}


def _log() -> SearchLog:
    entrada = SearchLogEntry(
        database="OpenAlex",
        db_key="openalex",
        kind="database",
        declared=True,
        status="ok",
        backend="openalex.search_openalex",
        started_utc=_HORA,
    )
    return SearchLog(
        started_utc=_HORA, finished_utc=_HORA, max_results=50, mailto_set=False, entries=[entrada]
    )


def _meta():
    efectos = load_protocol_files(EXAMPLE).effects
    assert efectos is not None
    return meta_analyze(efectos.effects, efectos.measure)


# ── D1 · el meta-análisis sale de effects.yml, no de la extracción ───────────


def test_metodos_dicen_de_donde_sale_el_meta_analisis_y_avisan_sin_incluidos() -> None:
    meta = _meta()
    protocol = load_protocol(EXAMPLE)

    sin_incluidos = render_methods(
        protocol=protocol, counts=PrismaCounts(), meta_result=meta, included_ids=[]
    )
    parcial = render_methods(
        protocol=protocol,
        counts=PrismaCounts(),
        meta_result=meta,
        included_ids=["estudio-bogota-2019", "estudio-lima-2020"],
    )
    todos = render_methods(
        protocol=protocol,
        counts=PrismaCounts(),
        meta_result=meta,
        included_ids=[s.study_id for s in meta.studies],
    )

    declarado = (
        "meta-análisis de los efectos declarados en `effects.yml` (k = 4), no derivados de la "
        "extracción de esta corrida"
    )
    assert declarado in sin_incluidos and declarado in todos
    assert "cuantitativa (meta-análisis)" not in sin_incluidos
    assert "⚠ la corrida no incluyó ningún estudio" in sin_incluidos
    assert "⚠ 2 de los 4 estudios del meta-análisis no están entre los incluidos" in parcial
    assert "⚠" not in todos.split("### Síntesis")[1].split("###")[0]


def test_corrida_demo_declara_el_meta_analisis_ajeno_a_sus_incluidos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def busqueda(_query: str, _n: int) -> list[SearchRecord]:
        return [SearchRecord(record_id="rec-1", title="LLM screening", source_db="OpenAlex")]

    monkeypatch.setattr(pipeline_mod, "build_provider", lambda _cfg: ScriptedProvider())
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")
    run_pipeline(
        protocol, EXAMPLE, ctx, auto_approve=True, search_fn=busqueda, fetch_fn=fetch_disponible
    )

    metodos = (ctx.run_dir / "deliverable" / "metodologia.md").read_text(encoding="utf-8")
    assert "efectos declarados en `effects.yml` (k = 4)" in metodos
    assert "⚠ 4 de los 4 estudios del meta-análisis no están entre los incluidos" in metodos


# ── D2 · la fecha tecleada se rotula como declarada; la del motor es la registrada ──


def _protocolo_con_ventana() -> ReviewProtocol:
    return ReviewProtocol.model_validate(
        {
            "slug": "d",
            "title": "D",
            "question": {"text": "¿X?", "framework": "PEO"},
            "search_window": {"from": "2015-01-01", "to": "2026-06-30", "executed": "2026-06-26"},
        }
    )


def test_metodos_y_traice_rotulan_la_fecha_tecleada_como_declarada() -> None:
    protocol = _protocolo_con_ventana()

    metodos = render_methods(protocol=protocol, counts=PrismaCounts(), search_log=_log())
    traice = render_traice_checklist(
        [], _EFECTIVA, search_window=protocol.search_window, search_log=_log()
    )

    for texto in (metodos, traice):
        assert "executed: 2026-06-26" not in texto
        assert "ejecución declarada en el protocolo: 2026-06-26" in texto
    assert "Búsqueda ejecutada (fecha registrada por el motor): 2026-10-04." in metodos
    assert "fecha registrada por el motor: 2026-10-04" in traice
    # Sin log (corrida v0.7) no hay fecha del motor: la ventana sale como se declaró.
    assert "executed: 2026-06-26" in render_methods(protocol=protocol, counts=PrismaCounts())


# ── D3 · con --auto-approve el reporte lo aprobará la demo ───────────────────


def test_auto_approve_dice_que_el_reporte_lo_aprobara_la_demo() -> None:
    protocol = load_protocol(EXAMPLE)
    previsto = "aprobación de demostración prevista (--auto-approve): NO es una validación humana"

    traice = render_traice_checklist([], _EFECTIVA, auto_approve=True)
    metodos = render_methods(protocol=protocol, counts=PrismaCounts(), auto_approve=True)
    forzado = render_traice_checklist([], _EFECTIVA, auto_approve=True, forced_human=True)

    assert f"- reporte (A1): {previsto}" in traice
    assert f"Reporte final: {previsto} (autonomía A1)." in metodos
    assert "pendiente de la decisión final" not in traice + metodos
    # Con citas marcadas el gate exige humano e ignora --auto-approve (D8).
    assert "- reporte (A1): pendiente de la decisión final · exige decisión humana" in forzado
    assert previsto not in forzado


# ── D4 · «rescate» solo para un no recuperado evaluado por el revisor ────────


def test_rescate_es_solo_el_no_recuperado_y_la_reversion_tiene_su_nombre() -> None:
    exclusiones = ExclusionBreakdown(
        total_excluded=3,
        excluded_ai=2,
        excluded_human=1,
        overridden_to_include=1,
        overridden_to_exclude=0,
    )
    protocol = load_protocol(EXAMPLE)

    metodos = render_methods(
        protocol=protocol,
        counts=PrismaCounts(fulltext_sought=3, fulltext_rescued=1, fulltext_assessed=3),
        exclusions=exclusiones,
    )
    traice = render_traice_checklist([], _EFECTIVA, exclusions=exclusiones)

    assert "exclusiones de la IA revertidas por un humano=1" in metodos
    assert "Informes rescatados por el revisor: 1 que el motor no recuperó" in metodos
    assert "rescatados por humano" not in metodos
    assert "- Exclusiones de la IA revertidas por un humano (IA excluía, humano incluyó): 1" in (
        traice
    )
    assert "Excluidos por IA (sin revertir por un humano): 2" in traice
    assert "escat" not in traice  # ni «rescate» ni «rescatados» en trAIce


# ── D5 · detalles ────────────────────────────────────────────────────────────


def test_traice_no_repite_la_autonomia_del_reporte() -> None:
    traice = render_traice_checklist([], {**_EFECTIVA, "reporte": "A2"})

    assert "- reporte (A2): auto-proceed previsto: sin revisión humana" in traice
    assert "(A2): auto-proceed previsto (A2)" not in traice


def test_metodos_dicen_modelo_si_no_hay_ensemble() -> None:
    from revisia.metrics import compute_screening_metrics

    metricas = compute_screening_metrics([], {}, fn_weight=10.0)
    con_ensemble = load_protocol(EXAMPLE)
    sin_ensemble = con_ensemble.model_copy(update={"ensemble": [], "ensemble_llm": {}})

    assert "se mide la propuesta del ensemble" in render_methods(
        protocol=con_ensemble, counts=PrismaCounts(), metrics=metricas
    )
    uno = render_methods(protocol=sin_ensemble, counts=PrismaCounts(), metrics=metricas)
    assert "se mide la propuesta del modelo" in uno
    assert "ensemble, no la decisión" not in uno


def test_prisma_s_item_1_distingue_las_bases_importadas_a_mano() -> None:
    markdown = render_prisma_s_checklist(databases=["OpenAlex", "Scopus", "CINAHL"])
    item_1 = next(x for x in markdown.splitlines() if x.startswith("- [ ] 1."))

    assert "Bases: OpenAlex (APIs abiertas; ver docs/integraciones.md)" in item_1
    assert "importadas manualmente vía imported/ (sin API en el motor): Scopus, CINAHL" in item_1
    assert "Scopus, CINAHL (APIs" not in item_1


def test_checklists_apuntan_a_la_copia_congelada_de_las_cadenas() -> None:
    item_7 = next(
        x for x in render_prisma_2020_checklist().splitlines() if x.startswith("- [ ] 7.")
    )
    item_8 = next(
        x
        for x in render_prisma_s_checklist(databases=["OpenAlex"]).splitlines()
        if x.startswith("- [ ] 8.")
    )

    for item in (item_7, item_8):
        assert "00_protocol/search_strings/" in item
        assert "protocols/<slug>/search_strings" not in item


def test_arquitectura_cita_el_paquete_del_auditor() -> None:
    texto = (ROOT / "docs" / "arquitectura.md").read_text(encoding="utf-8")

    assert "`audit/`" in texto
    assert "`audit.py`" not in texto


# ── D6 · `ran_in_engine` es público y lo comparten exports y auditor ─────────


def test_ran_in_engine_es_publico_y_el_auditor_usa_el_mismo() -> None:
    assert not hasattr(checklist_mod, "_ran_in_engine")
    assert checks_search.ran_in_engine is checklist_mod.ran_in_engine
