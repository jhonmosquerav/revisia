"""``arithmetic`` con los artefactos de la Ola 1: relaciones 1-13 de §4.4 (F2).

Cada caso rompe una relación de la corrida real (búsqueda, dedup, recuperación,
16b, CSV, diarios, métricas desde ``gold.json``) y comprueba que el auditor la
nombra. Las relaciones v0.7 siguen cubiertas en ``tests/test_audit_flujo.py``.

``arithmetic`` también tiene que pasar en las corridas que el motor de la Ola 1 produce de
verdad (spec 2026-10-04 §9.4: corridas reales, no fabricadas), no solo en la de referencia:
sin registros, sin incluidos, sin ningún texto completo recuperado (por un fallo transitorio,
que el motor no escribe en el diario, y por uno permanente), con rescates humanos (uno incluido
y otro excluido), sin 2.º extractor, interrumpida por un 429 a mitad del cribado T/A y del texto
completo y reanudada, con ``--auto-approve`` y con citas marcadas adjudicadas (también con el
juez de grounding, cuyas llamadas cuenta la relación 12). Sobre varias de ellas se rompe
después la relación que solo esa corrida ejercita.
"""

from __future__ import annotations

import csv
import io
import json
import shutil
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from audit_fixtures import auditar, edit_json, edit_yaml, fila
from conftest import GOLD_AUDITORIA, REGISTROS_AUDITORIA, etiquetar_auditoria, proveedor_auditoria
from fakes import ScriptedProvider, fetch_disponible, fetch_no_disponible
from hitl_helpers import correr_hasta

from revisia.agents.fulltext import FullText
from revisia.audit import CHECKS
from revisia.audit.artifacts import AuditContext, load_run
from revisia.audit.checks_flow import collect_relations
from revisia.config import load_protocol
from revisia.exclusions import compute_exclusion_breakdown
from revisia.exports import PrismaCounts, render_flow_diagram, render_flow_markdown
from revisia.llm.base import LLMRequest
from revisia.llm.registry import ProviderConfig
from revisia.orchestration import pipeline as pipeline_mod
from revisia.orchestration.pipeline import PipelineResult, run_pipeline
from revisia.orchestration.run_context import RunContext, RunInterrupted
from revisia.schemas.artifacts import JOURNAL_PATHS
from revisia.schemas.records import SearchRecord
from revisia.schemas.screening import ScreeningDecision


def _json(rel: str, fn: Callable) -> Callable[[Path], None]:
    def _editar(run: Path) -> None:
        edit_json(run / rel, fn)

    return _editar


def _counts(**cambios) -> Callable[[Path], None]:
    def _editar(run: Path) -> None:
        edit_yaml(run / "manifest.yml", lambda m: m["counts"].update(cambios))

    return _editar


def _quitar_del_manifiesto(clave: str) -> Callable[[dict], None]:
    # `del` y no `m.pop(...)`: `edit_yaml` sustituye el documento por el mapa que devuelve `fn`.
    def _editar(manifest: dict) -> None:
        del manifest[clave]

    return _editar


def _csv(clave: str, valor: str) -> Callable[[Path], None]:
    def _editar(run: Path) -> None:
        path = run / "deliverable" / "interop" / "prisma2020_flow.csv"
        rows = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8"))))
        header = rows[0]
        for row in rows[1:]:
            if row[header.index("data")] == clave:
                row[header.index("n")] = valor
        buf = io.StringIO()
        csv.writer(buf, lineterminator="\n").writerows(rows)
        path.write_text(buf.getvalue(), encoding="utf-8")

    return _editar


def _jsonl(rel: str, fn: Callable[[list[dict]], None]) -> Callable[[Path], None]:
    def _editar(run: Path) -> None:
        path = run / rel
        entries = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        fn(entries)
        text = "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries)
        path.write_text(text, encoding="utf-8")

    return _editar


def _quitar_ultimo(items: list) -> None:
    del items[-1]


def _no_disponible(rows: list[dict]) -> None:
    rows[0].update(available=False, reason="no_disponible", text_file=None, text_sha256=None)


def _invertir_origen(reports: list[dict]) -> None:
    for report in reports:
        report["reason_source"] = "ai" if report["reason_source"] == "human" else "human"


def _cambiar_respuesta(entries: list[dict]) -> None:
    entries[0]["metas"][0]["response_sha256"] = "0" * 64


def _quitar_un_voto(entries: list[dict]) -> None:
    del entries[0]["metas"][-1]


def _id_repetido(records: list[dict]) -> None:
    records[1]["record_id"] = records[0]["record_id"]


def _recortar_manifiesto(manifest: dict) -> None:
    del manifest["llm_calls"][-1]


def _rationale(decisions: list[dict]) -> None:
    decisions[0]["votes"][0]["rationale"] = "editado a mano"


def _campo_extraido(extractions: dict) -> None:
    primera = next(iter(extractions.values()))
    primera["extractor"] = "human:editora"


def _invertir_gold(gold: dict) -> None:
    gold["10.1000/cocina"] = True


RELACIONES_OLA1 = [
    pytest.param(
        _json("01_search/records.json", _quitar_ultimo),
        "1 · identified == len(01_search/records.json)",
        id="registros-de-la-busqueda",
    ),
    pytest.param(
        _json("01_search/records.json", lambda r: r[0].update(source_db="Crossref")),
        "1 · identified_by_source == Counter(source_db) de records.json",
        id="fuentes-de-la-busqueda",
    ),
    pytest.param(
        _json("02_dedup/dedup.json", lambda d: d.update(n_in=8)),
        "4 · dedup.n_in == identified",
        id="dedup-n-in",
    ),
    pytest.param(
        _json("02_dedup/dedup.json", lambda d: d.update(duplicates=[])),
        "4 · n_in − n_out == len(duplicates) == duplicates_removed",
        id="dedup-duplicados",
    ),
    pytest.param(
        _json("02_dedup/records.json", _id_repetido),
        "4 · ids de 02_dedup/records.json únicos",
        id="dedup-ids-repetidos",
    ),
    pytest.param(
        _json("03_screening/decisions.json", lambda d: d.reverse()),
        "5 · 03_screening/decisions.json en el orden de 02_dedup/records.json",
        id="orden-de-ta",
    ),
    pytest.param(
        _counts(fulltext_sought=5), "6 · fulltext_sought == screened − excluded_ta", id="sought"
    ),
    pytest.param(
        _counts(fulltext_not_retrieved=1),
        "8 · fulltext_assessed == fulltext_sought − fulltext_not_retrieved",
        id="no-recuperados",
    ),
    pytest.param(
        _json("04_fulltext/retrieval.json", _no_disponible),
        "7 · retrieved ⇔ retrieval.available ⇔ un voto",
        id="no-recuperado-cribado-por-ia",
    ),
    pytest.param(
        _json("04_fulltext/excluded.json", lambda r: r.clear()),
        "9 · excluded_ft == len(04_fulltext/excluded.json)",
        id="16b-vacia",
    ),
    pytest.param(
        _json("04_fulltext/excluded.json", lambda r: r[0].update(reason="otra razón")),
        "9 · ft_exclusion_reasons == Counter(reason) de excluded.json",
        id="16b-razones",
    ),
    pytest.param(
        _json("04_fulltext/excluded.json", _invertir_origen),
        "9 · reason_source == human ⇔ human_label == exclude",
        id="16b-origen",
    ),
    pytest.param(
        _counts(excluded_ft_ai=5),
        "9 · excluded_ft_human + excluded_ft_ai == excluded_ft",
        id="ft-humano-ia",
    ),
    pytest.param(
        _json("04_fulltext/decisions.json", lambda d: d[0].update(final_label="unclear")),
        "10 · included == #(final FT == include)",
        id="incluidos-ft",
    ),
    pytest.param(_csv("dbr_sought_reports", "9"), "11 · CSV dbr_sought_reports", id="csv-sought"),
    pytest.param(
        _csv("dbr_notretrieved_reports", "2"),
        "11 · CSV dbr_notretrieved_reports",
        id="csv-no-recuperados",
    ),
    pytest.param(
        _jsonl(JOURNAL_PATHS["screening_ta"], _cambiar_respuesta),
        "12 · metas de 03_screening/journal.jsonl en llm_calls.jsonl",
        id="meta-que-no-esta-en-llm-calls",
    ),
    pytest.param(
        _jsonl(JOURNAL_PATHS["screening_ta"], _quitar_un_voto),
        "12 · llamadas por línea en 03_screening/journal.jsonl",
        id="miembros-por-linea",
    ),
    pytest.param(
        _json("03_screening/decisions.json", _rationale),
        "13 · 03_screening/decisions.json == una línea de 03_screening/journal.jsonl",
        id="consolidado-ta",
    ),
    pytest.param(
        _json("05_extraction/extractions.json", _campo_extraido),
        "13 · 05_extraction/extractions.json == una línea de 05_extraction/journal.jsonl",
        id="consolidado-extraccion",
    ),
    pytest.param(
        lambda run: edit_yaml(run / "manifest.yml", _recortar_manifiesto),
        "§4.3 · manifest.llm_calls == líneas de llm_calls.jsonl",
        id="manifiesto-vs-llm-calls",
    ),
    pytest.param(
        _json("03_screening/gold.json", _invertir_gold),
        "§9.3 · matriz == recálculo desde decisions.json y gold.json",
        id="metricas-desde-gold",
    ),
]


@pytest.mark.parametrize(("romper", "relacion"), RELACIONES_OLA1)
def test_arithmetic_ola1_cada_relacion_rota_falla(corrida, romper, relacion: str) -> None:
    romper(corrida)
    arithmetic = fila(auditar(corrida), "arithmetic")
    assert arithmetic.status == "FAIL"
    assert relacion in arithmetic.detail


def test_arithmetic_corrida_de_la_ola_1_pasa_sin_relaciones_v07(corrida) -> None:
    arithmetic = fila(auditar(corrida), "arithmetic")
    assert arithmetic.status == "PASS"
    assert "v0.7" not in arithmetic.detail


# ── Más relaciones de la Ola 1 sobre la corrida de referencia ─────────────────────────────────


def _relaciones(run: Path) -> dict[str, tuple[bool | None, str]]:
    """Las relaciones de ``arithmetic`` (``nombre → (ok, detalle)``), sin nombres repetidos."""
    relaciones = collect_relations(AuditContext(load_run(run)))
    nombres = [r.name for r in relaciones]
    assert len(nombres) == len(set(nombres)), nombres
    return {r.name: (r.ok, r.detail) for r in relaciones}


def _rota(run: Path, relacion: str) -> str:
    """Audita ``run``, comprueba que ``arithmetic`` falla nombrando ``relacion`` y devuelve su
    detalle en ``collect_relations``."""
    arithmetic = fila(auditar(run), "arithmetic")
    assert arithmetic.status == "FAIL", arithmetic.detail
    ok, detalle = _relaciones(run)[relacion]
    assert ok is False, (relacion, ok, detalle)
    return detalle


def _decision_ft(rid: str, **cambios) -> Callable[[list[dict]], None]:
    def _editar(decisions: list[dict]) -> None:
        for decision in decisions:
            if decision["record_id"] == rid:
                decision.update(cambios)

    return _editar


def _sin_lineas(lineas: list[dict]) -> None:
    lineas.clear()


def _documento_editado(run: Path) -> None:
    path = run / "deliverable" / "documento.md"
    path.write_text("# Demo\n\nUna narrativa que ninguna llamada produjo.\n", encoding="utf-8")


def _quitar_llamada(run: Path, elegir: Callable[[dict], bool]) -> None:
    """Quita de ``llm_calls.jsonl`` y de su copia en el manifiesto las llamadas que ``elegir``
    marca, sin tocar los diarios (la copia del manifiesto sigue coincidiendo con el fichero)."""
    path = run / "llm_calls.jsonl"
    calls = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    kept = [c for c in calls if not elegir(c)]
    assert len(kept) < len(calls)
    path.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in kept), "utf-8")
    edit_yaml(run / "manifest.yml", lambda m: m.update(llm_calls=kept))


def _etapa_ajena(entries: list[dict]) -> None:
    entries[0]["stage"] = "extraccion"


OTRAS_RELACIONES = [
    pytest.param(
        _json("04_fulltext/retrieval.json", lambda rows: rows.reverse()),
        "7 · ids de 04_fulltext/retrieval.json == ids de 04_fulltext",
        id="orden-de-la-recuperacion",
    ),
    pytest.param(
        _json("04_fulltext/decisions.json", _decision_ft("10.1000/llm-1", final_label="unclear")),
        "7 · ningún final FT == unclear (lo resuelve un humano, D1)",
        id="unclear-sin-resolver",
    ),
    pytest.param(
        _json("04_fulltext/decisions.json", _decision_ft("10.1000/llm-1", final_label="exclude")),
        "7 · final_label FT == human_label or ensemble_label",
        id="final-ft-sin-humano",
    ),
    pytest.param(
        _json(
            "04_fulltext/decisions.json",
            _decision_ft("10.1000/llm-1", ensemble_label="unclear"),
        ),
        "7 · ensemble_label FT == propuesta de su voto (null si no se recuperó)",
        id="propuesta-ft-manipulada",
    ),
    pytest.param(
        _counts(excluded_ft_human=0, excluded_ft_ai=1),
        "9 · excluded_ft_human/ai == reason_source de excluded.json",
        id="16b-humano-ia-intercambiados",
    ),
    pytest.param(
        _json("04_fulltext/excluded.json", lambda r: r[0].update(title="Otro título")),
        "9 · 04_fulltext/excluded.json == compute_ft_excluded(04_fulltext/decisions.json)",
        id="16b-distinta-del-recalculo",
    ),
    pytest.param(
        _json("04_fulltext/decisions.json", _rationale),
        "13 · 04_fulltext/decisions.json == una línea de 04_fulltext/journal.jsonl",
        id="consolidado-ft",
    ),
    pytest.param(
        _json("07_rob/assessments.json", lambda a: next(iter(a.values())).update(overall="high")),
        "13 · 07_rob/assessments.json == una línea de 07_rob/journal.jsonl",
        id="consolidado-rob",
    ),
    pytest.param(
        _json("06_synthesis/verification.json", lambda v: v.update(notes="editado a mano")),
        "13 · 06_synthesis/verification.json == una línea de 06_synthesis/verification.jsonl",
        id="consolidado-verificacion",
    ),
    pytest.param(
        _json("04_fulltext/retrieval.json", lambda rows: rows[0].update(n_chars=1)),
        "13 · 04_fulltext/retrieval.json == una línea de 04_fulltext/retrieval.jsonl",
        id="consolidado-recuperacion",
    ),
    pytest.param(
        _documento_editado,
        "13 · deliverable/documento.md contiene la narrativa de una línea de "
        "06_synthesis/journal.jsonl",
        id="documento-sin-su-sintesis",
    ),
    pytest.param(
        _jsonl(JOURNAL_PATHS["extraccion_2"], _sin_lineas),
        "13 · 05_extraction/agreement.json respaldado por 05_extraction/journal_2.jsonl",
        id="doble-extraccion-sin-diario",
    ),
    pytest.param(
        lambda run: _quitar_llamada(run, lambda c: c["stage"] == "sintesis"),
        "12 · metas de 06_synthesis/journal.jsonl en llm_calls.jsonl",
        id="sintesis-sin-su-llamada",
    ),
    pytest.param(
        _jsonl(JOURNAL_PATHS["rob"], _etapa_ajena),
        "12 · metas de 07_rob/journal.jsonl en llm_calls.jsonl",
        id="linea-de-otra-etapa",
    ),
    pytest.param(
        lambda run: (run / "03_screening" / "gold.json").unlink(),
        "§9.3 · matriz == recálculo desde decisions.json y gold.json (ensemble_label, D6)",
        id="gold-ausente-con-metricas",
    ),
    pytest.param(
        _counts(fulltext_assessed=3),
        "8 · fulltext_assessed == #(final FT ≠ null)",
        id="evaluados-de-menos",
    ),
    pytest.param(
        _json("02_dedup/dedup.json", lambda d: d.update(n_out=5)),
        "4 · n_out == screened == len(02_dedup/records.json)",
        id="dedup-n-out",
    ),
    pytest.param(
        lambda run: (run / "01_search" / "records.json").unlink(),
        "1 · 01_search/records.json (identified, identified_by_source)",
        id="registros-de-la-busqueda-ausentes",
    ),
    pytest.param(
        lambda run: (run / "02_dedup" / "dedup.json").unlink(),
        "4 · 02_dedup/dedup.json (n_in, n_out, duplicates)",
        id="informe-del-dedup-ausente",
    ),
    pytest.param(
        lambda run: (run / "04_fulltext" / "retrieval.json").unlink(),
        "7 · retrieved ⇔ retrieval.available ⇔ un voto",
        id="recuperacion-ausente",
    ),
    pytest.param(
        lambda run: (run / "04_fulltext" / "excluded.json").unlink(),
        "9 · lista 16b (04_fulltext/excluded.json)",
        id="16b-ausente",
    ),
]


@pytest.mark.parametrize(("romper", "relacion"), OTRAS_RELACIONES)
def test_arithmetic_ola1_otras_relaciones_rotas_fallan(corrida, romper, relacion: str) -> None:
    romper(corrida)
    _rota(corrida, relacion)


# La relación 12 en cada diario con llamadas de la corrida de referencia (el de verificación, en
# la corrida con juez de grounding; el de la recuperación no tiene llamadas: una meta suya no
# valida `LLMCall` y la marca `schemas`).
DIARIOS_CON_LLAMADAS = ["screening_ta", "screening_ft", "extraccion", "extraccion_2", "rob"]


@pytest.mark.parametrize("etapa", [*DIARIOS_CON_LLAMADAS, "sintesis"])
def test_arithmetic_meta_de_un_diario_fuera_de_llm_calls_falla(corrida, etapa: str) -> None:
    _jsonl(JOURNAL_PATHS[etapa], _cambiar_respuesta)(corrida)
    _rota(corrida, f"12 · metas de {JOURNAL_PATHS[etapa]} en llm_calls.jsonl")


@pytest.mark.parametrize("etapa", [*DIARIOS_CON_LLAMADAS, "sintesis"])
def test_arithmetic_linea_de_diario_sin_su_llamada_falla(corrida, etapa: str) -> None:
    _jsonl(JOURNAL_PATHS[etapa], _quitar_un_voto)(corrida)
    detalle = _rota(corrida, f"12 · llamadas por línea en {JOURNAL_PATHS[etapa]}")
    assert "(se esperan " in detalle


def test_arithmetic_diario_de_recuperacion_con_una_llamada_falla(corrida) -> None:
    # La recuperación no llama a ninguna IA: una meta (válida, de otra etapa) en su diario rompe
    # las dos relaciones 12 de ese diario.
    texto_ft = (corrida / JOURNAL_PATHS["screening_ft"]).read_text(encoding="utf-8")
    meta_ft = json.loads(texto_ft.splitlines()[0])["metas"][0]
    path = JOURNAL_PATHS["fulltext_retrieval"]
    _jsonl(path, lambda entries: entries[0].update(metas=[meta_ft]))(corrida)
    _rota(corrida, f"12 · metas de {path} en llm_calls.jsonl")
    detalle = _rota(corrida, f"12 · llamadas por línea en {path}")
    assert "línea 1: 1 (se esperan 0)" in detalle


def test_arithmetic_meta_de_otro_registro_falla(corrida) -> None:
    def _otro_registro(entries: list[dict]) -> None:
        entries[0]["metas"][0]["record_id"] = entries[1]["record_id"]

    _jsonl(JOURNAL_PATHS["screening_ta"], _otro_registro)(corrida)
    detalle = _rota(corrida, "12 · metas de 03_screening/journal.jsonl en llm_calls.jsonl")
    assert "meta de otra etapa o registro" in detalle


def test_arithmetic_metricas_ausentes_con_gold_falla(corrida) -> None:
    (corrida / "03_screening" / "metrics.json").unlink()
    edit_yaml(corrida / "manifest.yml", _quitar_del_manifiesto("screening_metrics"))
    detalle = _rota(corrida, "§9.3 · metrics.json junto a gold.json")
    assert "03_screening/metrics.json ausente" in detalle


def test_arithmetic_ola1_no_aplica_las_relaciones_v07(corrida) -> None:
    nombres = list(_relaciones(corrida))
    assert [n for n in nombres if n.startswith("v0.7")] == []
    for numero in ("1 ·", "4 ·", "5 ·", "6 ·", "7 ·", "8 ·", "9 ·", "10 ·", "11 ·", "12 ·", "13 ·"):
        assert any(n.startswith(numero) for n in nombres), numero


def test_arithmetic_diario_ausente_con_su_consolidado_es_relacion_rota(corrida) -> None:
    (corrida / JOURNAL_PATHS["rob"]).unlink()
    detalle = _rota(corrida, "13 · 07_rob/assessments.json == una línea de 07_rob/journal.jsonl")
    assert detalle.startswith("07_rob/journal.jsonl ausente")
    assert "(el motor siempre lo escribe)" in detalle


def test_arithmetic_diario_con_una_linea_invalida_es_no_verificable(corrida) -> None:
    # Una línea que no valida la marca `schemas`: lo que dependa de ella es no verificable, no
    # «rota» (ni verificado).
    _jsonl(JOURNAL_PATHS["rob"], lambda e: e[0].pop("input_sha256"))(corrida)
    report = auditar(corrida)
    assert fila(report, "schemas").status == "FAIL"
    relaciones = _relaciones(corrida)
    ok, detalle = relaciones["13 · 07_rob/assessments.json == una línea de 07_rob/journal.jsonl"]
    assert ok is None
    assert "ver `schemas`" in detalle
    assert relaciones["12 · metas de 07_rob/journal.jsonl en llm_calls.jsonl"][0] is None
    assert fila(report, "arithmetic").status == "WARN"


def test_arithmetic_diario_ilegible_deja_sus_relaciones_no_verificables(corrida) -> None:
    (corrida / JOURNAL_PATHS["screening_ta"]).write_bytes("hola".encode("utf-16"))
    relaciones = _relaciones(corrida)
    for nombre in (
        "12 · metas de 03_screening/journal.jsonl en llm_calls.jsonl",
        "12 · llamadas por línea en 03_screening/journal.jsonl",
        "13 · 03_screening/decisions.json == una línea de 03_screening/journal.jsonl",
    ):
        ok, detalle = relaciones[nombre]
        assert ok is None, nombre
        assert "ilegible" in detalle
    assert fila(auditar(corrida), "schemas").status == "FAIL"


def test_arithmetic_llm_calls_ilegible_deja_la_relacion_12_no_verificable(corrida) -> None:
    (corrida / "llm_calls.jsonl").write_bytes("hola".encode("utf-16"))
    relaciones = _relaciones(corrida)
    ok, detalle = relaciones["12 · metas de 03_screening/journal.jsonl en llm_calls.jsonl"]
    assert ok is None
    assert "llm_calls.jsonl ilegible" in detalle
    # Lo que no depende de llm_calls.jsonl se sigue verificando.
    assert relaciones["12 · llamadas por línea en 03_screening/journal.jsonl"][0] is True
    assert fila(auditar(corrida), "arithmetic").status == "WARN"


def test_arithmetic_llm_calls_ausente_con_metas_en_los_diarios_falla(corrida) -> None:
    (corrida / "llm_calls.jsonl").unlink()
    detalle = _rota(corrida, "12 · metas de 03_screening/journal.jsonl en llm_calls.jsonl")
    assert "llm_calls.jsonl ausente" in detalle


def test_arithmetic_ola1_valores_hostiles_se_acotan(corrida) -> None:
    def _hostil(entries: list[dict]) -> None:
        for i, entry in enumerate(entries):
            entry["record_id"] = f"{'r' * 50_000}-{i}"

    _jsonl(JOURNAL_PATHS["screening_ta"], _hostil)(corrida)
    edit_json(corrida / "01_search" / "records.json", lambda r: r[0].update(source_db="s" * 50_000))
    edit_json(corrida / "04_fulltext" / "excluded.json", lambda r: r[0].update(reason="x" * 50_000))
    report = auditar(corrida)
    arithmetic = fila(report, "arithmetic")
    assert arithmetic.status == "FAIL"
    assert "error interno" not in arithmetic.detail
    assert len(arithmetic.detail) < 1_500
    assert len(report.checks) == len(CHECKS)
    for nombre, (_, detalle) in _relaciones(corrida).items():
        assert len(detalle) < 1_000, nombre


# ── Corridas reales de la Ola 1 (spec §9.4): `arithmetic` pasa en todas ───────────────────────

_POR_ID = {r.record_id: r for r in REGISTROS_AUDITORIA}
IRRELEVANTES = (_POR_ID["10.1000/cocina"], _POR_ID["10.1000/botanica"])
SECUNDARIO = (_POR_ID["10.1000/secundario"],)
SIN_TEXTO = tuple(r.record_id for r in REGISTROS_AUDITORIA)
# Dos informes sin texto completo que la revisora rescata: uno lo incluye y otro lo excluye.
RESCATES: dict[str, dict] = {
    "10.1000/asreview": {
        "label": "include",
        "reason": "PDF conseguido por préstamo interbibliotecario",
    },
    "10.1000/ensemble": {
        "label": "exclude",
        "reason": "el texto conseguido no informa el desenlace",
    },
}
# Una síntesis que cita un año (`[2019]`, que el verificador toma por un id) y un incluido.
SINTESIS_CON_CITAS = "El cribado con LLM logra un recall alto [10.1000/llm-1]; ver también [2019]."
SINTESIS_CON_DOS_CITAS = "Recall alto [10.1000/llm-1], menos carga [10.1000/asreview]; ver [2019]."
RAZON_FALSO_POSITIVO = "es un año, no un estudio: falso positivo del patrón de citas"


def _fetch_transitorio(record: SearchRecord) -> FullText:
    """Toda recuperación falla por la red (``error_http``: transitorio, no va al diario)."""
    return FullText(
        text=record.abstract or "", available=False, reason="error_http", detail="503 caída"
    )


def _rescatar(stage: str, solicitud: dict) -> dict | None:
    """La revisora de referencia, que además rescata los informes de ``RESCATES``."""
    extra = etiquetar_auditoria(stage, solicitud)
    if stage != "screening_ft":
        return extra
    records = dict((extra or {}).get("records", {}))
    for record_id, etiqueta in RESCATES.items():
        assert record_id in solicitud["rescuable"], solicitud["rescuable"]
        records[record_id] = etiqueta
    return {"records": records}


def _adjudicar(stage: str, solicitud: dict) -> dict | None:
    """La revisora de referencia, que en el reporte adjudica cada cita marcada (D8)."""
    if stage != "reporte":
        return etiquetar_auditoria(stage, solicitud)
    marcadas = solicitud["must_adjudicate"]
    assert marcadas, "la síntesis debía tener citas marcadas"
    return {
        "flags": {
            str(i): {"verdict": "false_positive", "reason": RAZON_FALSO_POSITIVO} for i in marcadas
        }
    }


def _proveedor_que_cita(cfg: ProviderConfig) -> ScriptedProvider:
    proveedor = proveedor_auditoria(cfg)
    proveedor.sintesis = SINTESIS_CON_CITAS
    return proveedor


class _Caidas:
    """Un 429 en la llamada ``n`` de un modelo, una sola vez, contando entre invocaciones."""

    def __init__(self, plan: dict[str, int]) -> None:
        self.plan = plan
        self.cuenta: Counter[str] = Counter()

    def proveedor(self, cfg: ProviderConfig) -> ScriptedProvider:
        return _ProveedorConCaidas(proveedor_auditoria(cfg), self)


class _ProveedorConCaidas(ScriptedProvider):
    def __init__(self, base: ScriptedProvider, caidas: _Caidas) -> None:
        super().__init__(model=base.model, palabras=base.palabras, sintesis=base.sintesis)
        self._caidas = caidas

    def _llamar(self, req: LLMRequest) -> None:
        super()._llamar(req)
        self._caidas.cuenta[self.model] += 1
        if self._caidas.plan.get(self.model) == self._caidas.cuenta[self.model]:
            raise RuntimeError("429 Too Many Requests")


def _protocolo(base: Path, origen: Path, editar: Callable[[dict], None]) -> Path:
    """Copia del protocolo de la auditoría con ``protocol.yml`` editado."""
    destino = base / origen.name
    shutil.copytree(origen, destino)
    path = destino / "protocol.yml"
    crudo = yaml.safe_load(path.read_text(encoding="utf-8"))
    editar(crudo)
    path.write_text(yaml.safe_dump(crudo, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return destino


def _sin_segundo_extractor(crudo: dict) -> None:
    del crudo["ensemble_llm"]["extraccion"]


def _juez_de_grounding(crudo: dict) -> None:
    crudo["grounding"] = "agent"


def _completar(
    base: Path,
    protocolo: Path,
    *,
    registros: tuple[SearchRecord, ...] = REGISTROS_AUDITORIA,
    fetch: Callable[[SearchRecord], FullText] | None = None,
    etiquetar: Callable[[str, dict], dict | None] = etiquetar_auditoria,
    proveedor: Callable[[ProviderConfig], ScriptedProvider] = proveedor_auditoria,
    auto_approve: bool = False,
) -> Path:
    """Corre el pipeline real hasta completarlo, reanudando tras cada interrupción (D14)."""
    protocol = load_protocol(protocolo)
    ctx = RunContext(protocol.slug, base / "runs", datetime.now(UTC).strftime("%Y%m%d-%H%M%S"))

    def _busqueda(_query: str, n: int) -> list[SearchRecord]:
        return [r.model_copy(deep=True) for r in registros[:n]]

    resultado: PipelineResult | None = None
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pipeline_mod, "build_provider", proveedor)
        contexto = ctx
        for _ in range(6):
            try:
                if auto_approve:
                    resultado = run_pipeline(
                        protocol,
                        protocolo,
                        contexto,
                        auto_approve=True,
                        search_fn=_busqueda,
                        fetch_fn=fetch or fetch_disponible,
                    )
                else:
                    resultado = correr_hasta(
                        protocol,
                        protocolo,
                        contexto,
                        search_fn=_busqueda,
                        fetch_fn=fetch or fetch_disponible,
                        etiquetar=etiquetar,
                    )
                break
            except RunInterrupted:
                contexto = RunContext.open(ctx.run_dir)
    assert resultado is not None and resultado.status == "completed", resultado
    return ctx.run_dir


def _sin_incluidos_en_ta(base: Path, protocolo: Path) -> Path:
    return _completar(base, protocolo, registros=IRRELEVANTES)


def _sin_incluidos_en_ft(base: Path, protocolo: Path) -> Path:
    return _completar(base, protocolo, registros=SECUNDARIO)


def _ningun_texto_transitorio(base: Path, protocolo: Path) -> Path:
    return _completar(base, protocolo, fetch=_fetch_transitorio)


def _ningun_texto_permanente(base: Path, protocolo: Path) -> Path:
    return _completar(base, protocolo, fetch=fetch_no_disponible(SIN_TEXTO))


def _rescates(base: Path, protocolo: Path) -> Path:
    return _completar(base, protocolo, fetch=fetch_no_disponible(RESCATES), etiquetar=_rescatar)


def _sin_segundo_extractor_corrida(base: Path, protocolo: Path) -> Path:
    return _completar(base, _protocolo(base, protocolo, _sin_segundo_extractor))


def _interrumpida_y_reanudada(base: Path, protocolo: Path) -> Path:
    # `fake-b` es el 2.º miembro del ensemble T/A: su 2.ª llamada falla a mitad del 2.º
    # registro, con la del 1.er miembro ya pagada (y fuera de llm_calls.jsonl: el registro se
    # recalcula al reanudar). `fake-1` es el proveedor del texto completo: su 2.ª llamada es la
    # del 2.º informe recuperado.
    caidas = _Caidas({"fake-b": 2, "fake-1": 2})
    run = _completar(base, protocolo, proveedor=caidas.proveedor)
    info = json.loads((run / "run.json").read_text(encoding="utf-8"))
    assert [i["stage"] for i in info["interruptions"]] == ["screening_ta", "screening_ft"]
    return run


def _auto_approve(base: Path, protocolo: Path) -> Path:
    return _completar(base, protocolo, auto_approve=True)


def _citas_marcadas(base: Path, protocolo: Path) -> Path:
    return _completar(base, protocolo, proveedor=_proveedor_que_cita, etiquetar=_adjudicar)


def _juez(base: Path, protocolo: Path) -> Path:
    return _completar(
        base,
        _protocolo(base, protocolo, _juez_de_grounding),
        proveedor=_proveedor_que_cita,
        etiquetar=_adjudicar,
    )


def _juez_interrumpido(base: Path, protocolo: Path) -> Path:
    # `fake-1` hace el texto completo (4), la extracción (3), RoB (3) y la síntesis (1): sus
    # llamadas 12 y 13 son las del juez, una por cita del corpus. La 13 falla con la 12 ya pagada
    # (y fuera de llm_calls.jsonl: la verificación se recalcula entera al reanudar).
    caidas = _Caidas({"fake-1": 13})

    def _proveedor(cfg: ProviderConfig) -> ScriptedProvider:
        proveedor = caidas.proveedor(cfg)
        proveedor.sintesis = SINTESIS_CON_DOS_CITAS
        return proveedor

    run = _completar(
        base,
        _protocolo(base, protocolo, _juez_de_grounding),
        proveedor=_proveedor,
        etiquetar=_adjudicar,
    )
    info = json.loads((run / "run.json").read_text(encoding="utf-8"))
    assert [i["stage"] for i in info["interruptions"]] == ["sintesis"]
    return run


def _protocolo_con_gold(base: Path, origen: Path, gold: dict[str, bool] | None) -> Path:
    """Copia del protocolo de la auditoría con otro ``gold.yml`` (``None``: sin gold)."""
    destino = base / origen.name
    shutil.copytree(origen, destino)
    if gold is None:
        (destino / "gold.yml").unlink()
    else:
        (destino / "gold.yml").write_text(
            yaml.safe_dump({"gold": gold}, allow_unicode=True), encoding="utf-8"
        )
    return destino


def _sin_gold(base: Path, protocolo: Path) -> Path:
    return _completar(base, _protocolo_con_gold(base, protocolo, None))


def _recall_bajo(base: Path, protocolo: Path) -> Path:
    # `cocina` es relevante para el gold pero la IA la excluye: recall 4/5 = 0,80 < 0,95.
    gold = {**GOLD_AUDITORIA, "10.1000/cocina": True}
    return _completar(base, _protocolo_con_gold(base, protocolo, gold))


ESCENARIOS: dict[str, Callable[[Path, Path], Path]] = {
    "sin-gold": _sin_gold,
    "recall-bajo": _recall_bajo,
    "sin-incluidos-en-ta": _sin_incluidos_en_ta,
    "sin-incluidos-en-ft": _sin_incluidos_en_ft,
    "ningun-texto-transitorio": _ningun_texto_transitorio,
    "ningun-texto-permanente": _ningun_texto_permanente,
    "rescates": _rescates,
    "sin-segundo-extractor": _sin_segundo_extractor_corrida,
    "interrumpida-y-reanudada": _interrumpida_y_reanudada,
    "auto-approve": _auto_approve,
    "citas-marcadas": _citas_marcadas,
    "juez-de-grounding": _juez,
    "juez-interrumpido-y-reanudado": _juez_interrumpido,
}

# Conteos que prueban que cada corrida es la que dice ser.
CONTEOS: dict[str, dict[str, int]] = {
    "sin-gold": {"screened": 6, "included": 3},
    "recall-bajo": {"screened": 6, "included": 3},
    "sin-incluidos-en-ta": {"screened": 2, "excluded_ta": 2, "fulltext_sought": 0, "included": 0},
    "sin-incluidos-en-ft": {"fulltext_sought": 1, "excluded_ft": 1, "included": 0},
    "ningun-texto-transitorio": {
        "fulltext_sought": 4,
        "fulltext_not_retrieved": 4,
        "fulltext_assessed": 0,
        "included": 0,
    },
    "ningun-texto-permanente": {
        "fulltext_sought": 4,
        "fulltext_not_retrieved": 4,
        "fulltext_assessed": 0,
        "included": 0,
    },
    "rescates": {
        "fulltext_sought": 4,
        "fulltext_not_retrieved": 0,
        "fulltext_rescued": 2,
        "fulltext_assessed": 4,
        "excluded_ft": 2,
        "excluded_ft_human": 2,
        "included": 2,
    },
    "sin-segundo-extractor": {"included": 3},
    "interrumpida-y-reanudada": {"screened": 6, "fulltext_assessed": 4, "included": 3},
    "auto-approve": {"excluded_ft_ai": 1, "excluded_ft_human": 0, "included": 3},
    "citas-marcadas": {"included": 3},
    "juez-de-grounding": {"included": 3},
    "juez-interrumpido-y-reanudado": {"included": 3},
}


@pytest.fixture(scope="module")
def corrida_real(
    tmp_path_factory: pytest.TempPathFactory, protocolo_auditoria: Path
) -> Callable[[str], Path]:
    """Corridas reales de ``ESCENARIOS``, generadas una vez por módulo (no se editan)."""
    cache: dict[str, Path] = {}

    def _obtener(nombre: str) -> Path:
        if nombre not in cache:
            cache[nombre] = ESCENARIOS[nombre](tmp_path_factory.mktemp(nombre), protocolo_auditoria)
        return cache[nombre]

    return _obtener


@pytest.fixture
def copia_real(corrida_real: Callable[[str], Path], tmp_path: Path) -> Callable[[str], Path]:
    """Copia propia de una corrida de ``ESCENARIOS``, para romperla."""

    def _copiar(nombre: str) -> Path:
        origen = corrida_real(nombre)
        destino = tmp_path / "runs" / origen.name
        shutil.copytree(origen, destino)
        return destino

    return _copiar


def _manifiesto(run: Path) -> dict:
    return yaml.safe_load((run / "manifest.yml").read_text(encoding="utf-8"))


@pytest.mark.parametrize("nombre", list(ESCENARIOS))
def test_arithmetic_pasa_en_las_corridas_reales_de_la_ola_1(corrida_real, nombre: str) -> None:
    run = corrida_real(nombre)
    counts = _manifiesto(run)["counts"]
    assert {k: counts[k] for k in CONTEOS[nombre]} == CONTEOS[nombre]
    arithmetic = fila(auditar(run), "arithmetic")
    assert arithmetic.status == "PASS", arithmetic.detail
    assert "v0.7" not in arithmetic.detail
    assert all(ok is True for ok, _ in _relaciones(run).values())


def test_arithmetic_pasa_en_la_corrida_sin_registros(corrida_sin_registros) -> None:
    arithmetic = fila(auditar(corrida_sin_registros), "arithmetic")
    assert arithmetic.status == "PASS", arithmetic.detail
    assert _manifiesto(corrida_sin_registros)["counts"]["identified"] == 0


def test_corrida_transitoria_no_tiene_diario_de_recuperacion(corrida_real) -> None:
    # Reconciliación con la Tarea 12: el motor no escribe los fallos transitorios en el diario.
    run = corrida_real("ningun-texto-transitorio")
    assert not (run / JOURNAL_PATHS["fulltext_retrieval"]).exists()
    filas = json.loads((run / "04_fulltext" / "retrieval.json").read_text(encoding="utf-8"))
    assert {f["reason"] for f in filas} == {"error_http"}
    nombre = "13 · 04_fulltext/retrieval.json == una línea de 04_fulltext/retrieval.jsonl"
    assert _relaciones(run)[nombre][0] is True


def test_corrida_interrumpida_tiene_una_llamada_pagada_fuera_de_llm_calls(corrida_real) -> None:
    # Limitación conocida del motor (§4.3): la llamada del 1.er miembro sobre el registro en el
    # que cayó el 2.º no llega a llm_calls.jsonl; al reanudar el registro se recalcula entero. Por
    # eso la relación 12 es de inclusión (cada meta del diario está en llm_calls.jsonl), no de
    # igualdad.
    run = corrida_real("interrumpida-y-reanudada")
    lineas = (run / "llm_calls.jsonl").read_text(encoding="utf-8").splitlines()
    ta = Counter(json.loads(x)["record_id"] for x in lineas if '"screening_ta"' in x)
    assert set(ta.values()) == {2}  # 2 miembros por registro, sin la llamada perdida


def test_corrida_con_juez_cuenta_sus_llamadas_en_la_relacion_12(corrida_real) -> None:
    run = corrida_real("juez-de-grounding")
    (linea,) = (run / JOURNAL_PATHS["verificacion"]).read_text(encoding="utf-8").splitlines()
    entrada = json.loads(linea)
    existentes = [c for c in entrada["output"]["checks"] if c["exists_in_corpus"]]
    assert len(existentes) == 1  # el juez solo se llama para las citas del corpus (§14, 24c)
    assert len(entrada["metas"]) == 1


def test_corrida_con_el_juez_interrumpido_pierde_una_llamada_del_juez(corrida_real) -> None:
    # Como en el ensemble T/A: la primera llamada del juez de la verificación caída se pagó pero
    # no llegó a llm_calls.jsonl; al reanudar la verificación se recalcula y su línea lleva las
    # dos llamadas nuevas. La relación 12 (inclusión) la acepta.
    run = corrida_real("juez-interrumpido-y-reanudado")
    (linea,) = (run / JOURNAL_PATHS["verificacion"]).read_text(encoding="utf-8").splitlines()
    assert len(json.loads(linea)["metas"]) == 2
    lineas = (run / "llm_calls.jsonl").read_text(encoding="utf-8").splitlines()
    assert sum(json.loads(x)["stage"] == "verificacion" for x in lineas) == 2


# ── Romper en cada corrida la relación que solo ella ejercita ─────────────────────────────────


def _rescatado(run: Path, **cambios) -> None:
    edit_json(run / "04_fulltext" / "decisions.json", _decision_ft("10.1000/asreview", **cambios))


def _con_voto(decisions: list[dict]) -> None:
    for decision in decisions:
        if decision["record_id"] == "10.1000/asreview":
            decision["votes"] = [
                {
                    "model": "fake:fake-1",
                    "label": "include",
                    "confidence": 0.9,
                    "rationale": "guion: include",
                    "criteria_violated": [],
                }
            ]


def _quitar_meta_del_juez(entries: list[dict]) -> None:
    entries[0]["metas"].clear()


ROTURAS_EN_CORRIDAS_REALES = [
    pytest.param(
        "rescates",
        _counts(fulltext_rescued=0, fulltext_not_retrieved=2, fulltext_assessed=2),
        "8 · fulltext_rescued == #(no recuperado con humano)",
        id="rescates-declarados-como-no-recuperados",
    ),
    pytest.param(
        "rescates",
        _json("04_fulltext/decisions.json", _con_voto),
        "7 · retrieved ⇔ retrieval.available ⇔ un voto",
        id="rescate-con-voto-ia",
    ),
    pytest.param(
        "rescates",
        lambda run: _rescatado(run, human_reason=None),
        "7 · un rescate lleva human_reason (D2)",
        id="rescate-sin-razon",
    ),
    pytest.param(
        "rescates",
        lambda run: _rescatado(run, human_label=None, final_label=None, human_reason=None),
        "8 · fulltext_not_retrieved == #(no recuperado sin humano)",
        id="rescate-borrado",
    ),
    pytest.param(
        "ningun-texto-transitorio",
        _json("04_fulltext/retrieval.json", lambda rows: rows[0].update(reason="no_disponible")),
        "13 · 04_fulltext/retrieval.json == una línea de 04_fulltext/retrieval.jsonl",
        id="transitorio-convertido-en-permanente",
    ),
    pytest.param(
        "ningun-texto-permanente",
        _jsonl(JOURNAL_PATHS["fulltext_retrieval"], _quitar_ultimo),
        "13 · 04_fulltext/retrieval.json == una línea de 04_fulltext/retrieval.jsonl",
        id="permanente-sin-diario",
    ),
    pytest.param(
        "ningun-texto-permanente",
        _counts(fulltext_not_retrieved=0, fulltext_assessed=4),
        "8 · fulltext_not_retrieved == #(no recuperado sin humano)",
        id="no-recuperados-declarados-evaluados",
    ),
    pytest.param(
        "juez-de-grounding",
        _jsonl(JOURNAL_PATHS["verificacion"], _quitar_meta_del_juez),
        "12 · llamadas por línea en 06_synthesis/verification.jsonl",
        id="juez-sin-su-llamada",
    ),
    pytest.param(
        "juez-de-grounding",
        _jsonl(JOURNAL_PATHS["verificacion"], _cambiar_respuesta),
        "12 · metas de 06_synthesis/verification.jsonl en llm_calls.jsonl",
        id="juez-con-una-llamada-que-no-esta",
    ),
    pytest.param(
        "juez-interrumpido-y-reanudado",
        lambda run: _quitar_llamada(run, lambda c: c["stage"] == "verificacion"),
        "12 · metas de 06_synthesis/verification.jsonl en llm_calls.jsonl",
        id="juez-reanudado-sin-sus-llamadas",
    ),
    pytest.param(
        "interrumpida-y-reanudada",
        lambda run: _quitar_llamada(
            run, lambda c: c["stage"] == "screening_ta" and c["record_id"] == "10.1000/asreview"
        ),
        "12 · metas de 03_screening/journal.jsonl en llm_calls.jsonl",
        id="reanudada-sin-las-llamadas-del-registro-recalculado",
    ),
    pytest.param(
        "sin-incluidos-en-ft",
        _json("04_fulltext/excluded.json", lambda r: r[0].update(reason="otra razón")),
        "9 · ft_exclusion_reasons == Counter(reason) de excluded.json",
        id="sin-incluidos-razon-cambiada",
    ),
    pytest.param(
        "sin-incluidos-en-ta",
        _counts(fulltext_sought=1, fulltext_assessed=1),
        "6 · fulltext_sought == #(final T/A ∈ {include, unclear})",
        id="sin-incluidos-buscados-de-mas",
    ),
    pytest.param(
        "sin-segundo-extractor",
        _json("05_extraction/extractions.json", _campo_extraido),
        "13 · 05_extraction/extractions.json == una línea de 05_extraction/journal.jsonl",
        id="sin-segundo-extractor-extraccion-editada",
    ),
    pytest.param(
        "auto-approve",
        _json("04_fulltext/excluded.json", _invertir_origen),
        "9 · reason_source == human ⇔ human_label == exclude",
        id="auto-approve-exclusion-ia-como-humana",
    ),
    pytest.param(
        "citas-marcadas",
        _documento_editado,
        "13 · deliverable/documento.md contiene la narrativa de una línea de "
        "06_synthesis/journal.jsonl",
        id="citas-marcadas-documento-editado",
    ),
]


@pytest.mark.parametrize(("nombre", "romper", "relacion"), ROTURAS_EN_CORRIDAS_REALES)
def test_arithmetic_corrida_real_rota_falla_nombrando_la_relacion(
    copia_real, nombre: str, romper, relacion: str
) -> None:
    run = copia_real(nombre)
    romper(run)
    _rota(run, relacion)


def test_arithmetic_corrida_sin_registros_rota_falla(corrida_sin_registros) -> None:
    _counts(identified=1, identified_by_source={"OpenAlex": 1})(corrida_sin_registros)
    _rota(corrida_sin_registros, "1 · identified == len(01_search/records.json)")


# ── Corrección tras la revisión de la Tarea 14 ────────────────────────────────────────────────

RELACION_7 = "7 · retrieved ⇔ retrieval.available ⇔ un voto"
GOLD_Y_METRICAS = "§9.3 · metrics.json junto a gold.json"
GOLD_DEL_PROTOCOLO = "§9.3 · gold.json con el gold del protocolo"
RELACION_12_TA = "12 · metas de 03_screening/journal.jsonl en llm_calls.jsonl"
RELACION_13_DOCUMENTO = (
    "13 · deliverable/documento.md contiene la narrativa de una línea de 06_synthesis/journal.jsonl"
)
DIARIO_DENTRO_DEL_DEDUP = "4 · ids de 03_screening/journal.jsonl ⊆ ids de 02_dedup/records.json"


def _rotas(run: Path) -> list[str]:
    """Nombres de las relaciones rotas de ``arithmetic``."""
    return [nombre for nombre, (ok, _) in _relaciones(run).items() if ok is False]


def _lineas(run: Path, rel: str) -> list[dict]:
    texto = (run / rel).read_text(encoding="utf-8")
    return [json.loads(linea) for linea in texto.splitlines() if linea]


def _agregar_llamada(run: Path, llamada: dict) -> None:
    """Añade una llamada a ``llm_calls.jsonl`` y a su copia del manifiesto (sin tocar diarios)."""
    with (run / "llm_calls.jsonl").open("a", encoding="utf-8", newline="") as f:
        f.write(json.dumps(llamada, ensure_ascii=False) + "\n")
    edit_yaml(run / "manifest.yml", lambda m: m["llm_calls"].append(llamada))


# 1. Un rescate (informe no recuperado) no lleva votos de la IA ni propuesta (D2).


def _rescate_con_votos_de_la_ia(decisions: list[dict]) -> None:
    voto = {
        "model": "fake:fake-1",
        "label": "include",
        "confidence": 0.9,
        "rationale": "guion: include",
        "criteria_violated": [],
    }
    for decision in decisions:
        if decision["record_id"] == "10.1000/asreview":
            decision.update(votes=[voto, dict(voto)], ensemble_label="include")


def _rescate_con_propuesta_sin_votos(decisions: list[dict]) -> None:
    for decision in decisions:
        if decision["record_id"] == "10.1000/asreview":
            decision.update(ensemble_label="include")


@pytest.mark.parametrize(
    "tocar",
    [_rescate_con_votos_de_la_ia, _rescate_con_propuesta_sin_votos],
    ids=["dos-votos-de-la-ia", "propuesta-sin-votos"],
)
def test_arithmetic_rescate_con_votos_o_propuesta_de_la_ia_falla(copia_real, tocar) -> None:
    run = copia_real("rescates")
    _json("04_fulltext/decisions.json", tocar)(run)
    detalle = _rota(run, RELACION_7)
    assert "10.1000/asreview" in detalle


# 2. El gold del protocolo ancla las métricas: borrar gold.json y metrics.json no las evita.


def _borrar_gold_y_metricas(run: Path) -> None:
    (run / "03_screening" / "gold.json").unlink()
    (run / "03_screening" / "metrics.json").unlink()
    edit_yaml(run / "manifest.yml", _quitar_del_manifiesto("screening_metrics"))


def test_arithmetic_gold_y_metricas_borrados_con_recall_bajo_siguen_sin_publicarse(
    copia_real,
) -> None:
    run = copia_real("recall-bajo")
    legitima = auditar(run)
    assert fila(legitima, "thresholds").status == "FAIL"  # recall 0,80 < 0,95 (D7)
    assert legitima.publishable is False
    _borrar_gold_y_metricas(run)
    report = auditar(run)
    arithmetic = fila(report, "arithmetic")
    assert arithmetic.status == "FAIL", arithmetic.detail
    assert fila(report, "gold").status == "WARN"  # sin gold.json el check de calidad no ve nada
    assert report.publishable is False
    relaciones = _relaciones(run)
    assert relaciones[GOLD_Y_METRICAS][0] is False
    assert relaciones[GOLD_DEL_PROTOCOLO][0] is False
    assert "00_protocol/gold.yml" in relaciones[GOLD_Y_METRICAS][1]
    stage_artifacts = fila(report, "stage_artifacts")
    assert stage_artifacts.status == "FAIL"
    assert "03_screening/gold.json" in stage_artifacts.detail
    assert "03_screening/metrics.json" in stage_artifacts.detail


def test_arithmetic_solo_gold_json_borrado_con_gold_en_el_protocolo_falla(corrida) -> None:
    (corrida / "03_screening" / "gold.json").unlink()
    detalle = _rota(corrida, GOLD_DEL_PROTOCOLO)
    assert "03_screening/gold.json ausente" in detalle
    assert "(el motor siempre lo escribe)" in detalle


def test_arithmetic_gold_json_sin_un_id_del_gold_del_protocolo_falla(corrida) -> None:
    edit_json(corrida / "03_screening" / "gold.json", lambda gold: gold.pop("10.1000/cocina"))
    detalle = _rota(corrida, GOLD_DEL_PROTOCOLO)
    assert "10.1000/cocina" in detalle


def test_arithmetic_gold_json_puede_cambiar_valores_y_anadir_claves_con_gold_labels(
    corrida,
) -> None:
    # `gold_labels=` (D6) sobrescribe etiquetas del fichero y añade ids: las claves del gold del
    # protocolo siguen estando. La matriz sí cambia y la marca su propia relación.
    edit_json(
        corrida / "03_screening" / "gold.json",
        lambda gold: gold.update({"10.1000/cocina": True, "10.9/otro": False}),
    )
    assert _relaciones(corrida)[GOLD_DEL_PROTOCOLO][0] is True


@pytest.mark.parametrize(
    "texto",
    ["", "# plantilla sin etiquetar\n", "gold: {}\n", "gold:\n", "{}\n"],
    ids=["vacio", "solo-comentarios", "mapa-vacio", "gold-nulo", "mapa-plano-vacio"],
)
def test_arithmetic_gold_vacio_en_la_instantanea_no_exige_gold_ni_metricas(
    corrida, texto: str
) -> None:
    # El motor lee un `gold.yml` sin etiquetas como «sin gold» y no escribe gold.json ni
    # metrics.json: exigirlos sería un FAIL falso.
    (corrida / "00_protocol" / "gold.yml").write_text(texto, encoding="utf-8")
    _borrar_gold_y_metricas(corrida)
    arithmetic = fila(auditar(corrida), "arithmetic")
    assert arithmetic.status == "PASS", arithmetic.detail
    nombres = list(_relaciones(corrida))
    assert GOLD_Y_METRICAS not in nombres
    assert GOLD_DEL_PROTOCOLO not in nombres


def test_arithmetic_gold_plano_en_la_instantanea_tambien_se_exige(corrida) -> None:
    # El motor acepta `gold.yml` con el mapa `id → bool` en la raíz (`data.get("gold", data)`).
    gold = json.loads((corrida / "03_screening" / "gold.json").read_text(encoding="utf-8"))
    (corrida / "00_protocol" / "gold.yml").write_text(yaml.safe_dump(gold), encoding="utf-8")
    _borrar_gold_y_metricas(corrida)
    _rota(corrida, GOLD_Y_METRICAS)
    assert _relaciones(corrida)[GOLD_DEL_PROTOCOLO][0] is False


def test_arithmetic_gold_del_protocolo_ilegible_deja_la_relacion_no_verificable(corrida) -> None:
    (corrida / "00_protocol" / "gold.yml").write_text("gold: [sin: cerrar", encoding="utf-8")
    ok, detalle = _relaciones(corrida)[GOLD_DEL_PROTOCOLO]
    assert ok is None
    assert "00_protocol/gold.yml" in detalle


def test_arithmetic_corrida_sin_gold_no_tiene_gold_ni_metricas_y_pasa(corrida_real) -> None:
    run = corrida_real("sin-gold")
    assert not (run / "00_protocol" / "gold.yml").exists()
    assert not (run / "03_screening" / "gold.json").exists()
    assert not (run / "03_screening" / "metrics.json").exists()
    report = auditar(run)
    assert fila(report, "arithmetic").status == "PASS"
    assert fila(report, "stage_artifacts").status == "PASS"
    nombres = list(_relaciones(run))
    assert GOLD_Y_METRICAS not in nombres
    assert GOLD_DEL_PROTOCOLO not in nombres


# 3. Una narrativa vacía en el diario de síntesis no respalda cualquier documento.


def _sintesis_con_otra_linea(narrativa: str) -> Callable[[Path], None]:
    """Añade al diario de síntesis una línea con ``narrativa`` y una llamada propia."""

    def _editar(run: Path) -> None:
        linea = _lineas(run, JOURNAL_PATHS["sintesis"])[0]
        nueva = {**linea["metas"][0], "response_sha256": "e" * 64}
        _agregar_llamada(run, nueva)
        extra = {**linea, "input_sha256": "e" * 64, "output": {"narrative": narrativa}}
        extra["metas"] = [nueva]
        _jsonl(JOURNAL_PATHS["sintesis"], lambda lineas: lineas.append(extra))(run)

    return _editar


@pytest.mark.parametrize("narrativa", ["", "\n"], ids=["vacia", "salto"])
def test_arithmetic_narrativa_vacia_en_el_diario_no_respalda_cualquier_documento(
    corrida, narrativa: str
) -> None:
    _sintesis_con_otra_linea(narrativa)(corrida)
    _documento_editado(corrida)
    assert _rotas(corrida) == [RELACION_13_DOCUMENTO]


def test_arithmetic_narrativas_todas_en_blanco_dejan_el_documento_no_verificable(corrida) -> None:
    # Un motor cuyo modelo devuelve una síntesis vacía deja un documento sin narrativa: no hay
    # texto que contrastar, pero tampoco un FAIL falso (ni una relación verificada).
    _jsonl(JOURNAL_PATHS["sintesis"], lambda lineas: lineas[0]["output"].update(narrative=" "))(
        corrida
    )
    _documento_editado(corrida)
    ok, detalle = _relaciones(corrida)[RELACION_13_DOCUMENTO]
    assert ok is None
    assert "vacía" in detalle


# 5. Cada llamada de llm_calls.jsonl respalda una sola meta, y los miembros de T/A son distintos.


def test_arithmetic_meta_repetida_en_una_linea_de_ta_falla(corrida) -> None:
    # La meta del 2.º miembro se sustituye por la del 1.º, se borra la llamada real del 2.º y se
    # inyecta una huérfana: el número de llamadas y la cota inferior cuadran, pero una llamada
    # no puede respaldar dos posiciones.
    lineas = _lineas(corrida, JOURNAL_PATHS["screening_ta"])
    primera, segunda = lineas[0]["metas"]
    huerfana = {**primera, "record_id": lineas[1]["record_id"], "response_sha256": "b" * 64}
    _jsonl(JOURNAL_PATHS["screening_ta"], lambda e: e[0]["metas"].__setitem__(1, primera))(corrida)
    _quitar_llamada(corrida, lambda c: c == segunda)
    _agregar_llamada(corrida, huerfana)
    detalle = _rota(corrida, RELACION_12_TA)
    assert "línea 1" in detalle


def test_arithmetic_una_llamada_de_llm_calls_respalda_una_sola_meta(corrida) -> None:
    # Dos líneas de un mismo diario (aquí, la síntesis) citando la misma llamada.
    linea = _lineas(corrida, JOURNAL_PATHS["sintesis"])[0]
    extra = {**linea, "input_sha256": "d" * 64}
    _jsonl(JOURNAL_PATHS["sintesis"], lambda lineas: lineas.append(extra))(corrida)
    detalle = _rota(corrida, "12 · metas de 06_synthesis/journal.jsonl en llm_calls.jsonl")
    assert "línea 2" in detalle


def test_arithmetic_miembros_de_ta_con_el_mismo_rol_falla(corrida) -> None:
    # Dos llamadas reales (ambas en llm_calls.jsonl, del registro y la etapa) con el rol del
    # 1.er miembro: ni el número de metas ni su pertenencia lo delatan, el rol repetido sí.
    primera = _lineas(corrida, JOURNAL_PATHS["screening_ta"])[0]["metas"][0]
    gemela = {**primera, "response_sha256": "d" * 64}
    _agregar_llamada(corrida, gemela)
    _jsonl(JOURNAL_PATHS["screening_ta"], lambda e: e[0]["metas"].__setitem__(1, gemela))(corrida)
    detalle = _rota(corrida, RELACION_12_TA)
    assert "roles repetidos" in detalle


# 6. Un registro cribado no puede disfrazarse de duplicado: el diario de T/A cabe en el dedup.


def _registro_cribado_disfrazado_de_duplicado(run: Path) -> None:
    """Saca ``cocina`` de ``02_dedup/records.json`` y de las decisiones T/A, de forma coherente.

    Se ajustan el informe del dedup (un duplicado más), los conteos, el desglose de exclusiones,
    las métricas y el CSV: todas las relaciones de siempre cuadran, y el diario de T/A conserva
    la línea del registro que nadie pudo cribar.
    """
    rid = "10.1000/cocina"

    def _sin_el_registro(items: list[dict]) -> None:
        del items[_posicion(items, rid)]

    def _como_duplicado(dedup: dict) -> None:
        dedup["n_out"] -= 1
        dedup["duplicates"].append(
            {
                "record_id": rid,
                "source_db": "OpenAlex",
                "kept_record_id": "10.1000/llm-1",
                "key": "doi:x",
            }
        )

    edit_json(run / "02_dedup" / "records.json", _sin_el_registro)
    edit_json(run / "02_dedup" / "dedup.json", _como_duplicado)
    edit_json(run / "03_screening" / "decisions.json", _sin_el_registro)
    decisiones = [
        *json.loads((run / "03_screening" / "decisions.json").read_text(encoding="utf-8")),
        *json.loads((run / "04_fulltext" / "decisions.json").read_text(encoding="utf-8")),
    ]
    desglose = compute_exclusion_breakdown(
        [ScreeningDecision.model_validate(d) for d in decisiones]
    ).model_dump()
    (run / "03_screening" / "exclusions.json").write_text(json.dumps(desglose), encoding="utf-8")
    edit_json(
        run / "03_screening" / "metrics.json",
        lambda m: m.update(n=m["n"] - 1, tn=m["tn"] - 1),
    )
    metricas = json.loads((run / "03_screening" / "metrics.json").read_text(encoding="utf-8"))

    def _manifiesto(m: dict) -> None:
        m["exclusions"] = desglose
        m["screening_metrics"] = metricas
        counts = m["counts"]
        counts["duplicates_removed"] += 1
        counts["screened"] -= 1
        counts["excluded_ta"] -= 1
        counts["excluded_ta_ai"] -= 1

    edit_yaml(run / "manifest.yml", _manifiesto)
    counts = yaml.safe_load((run / "manifest.yml").read_text(encoding="utf-8"))["counts"]
    _csv("duplicates", str(counts["duplicates_removed"]))(run)
    _csv("records_screened", str(counts["screened"]))(run)
    _csv("records_excluded", str(counts["excluded_ta"]))(run)
    # El diagrama del entregable, rehecho con los conteos nuevos (lo compara la relación 16a).
    nuevos = PrismaCounts.model_validate(counts)
    (run / "deliverable" / "prisma_flow.md").write_text(
        render_flow_diagram(nuevos) + "\n\n" + render_flow_markdown(nuevos) + "\n",
        encoding="utf-8",
    )


def _posicion(items: list[dict], rid: str) -> int:
    return next(i for i, item in enumerate(items) if item["record_id"] == rid)


def test_arithmetic_registro_cribado_disfrazado_de_duplicado_falla(corrida) -> None:
    _registro_cribado_disfrazado_de_duplicado(corrida)
    # Es la única relación que lo delata: el resto de la aritmética cuadra.
    assert _rotas(corrida) == [DIARIO_DENTRO_DEL_DEDUP]
    detalle = _rota(corrida, DIARIO_DENTRO_DEL_DEDUP)
    assert "10.1000/cocina" in detalle


def test_arithmetic_diario_de_ta_dentro_del_dedup_se_verifica_en_la_corrida_real(corrida) -> None:
    assert _relaciones(corrida)[DIARIO_DENTRO_DEL_DEDUP][0] is True


def test_arithmetic_diario_de_ta_ausente_con_registros_cribados_es_relacion_rota(corrida) -> None:
    (corrida / JOURNAL_PATHS["screening_ta"]).unlink()
    ok, detalle = _relaciones(corrida)[DIARIO_DENTRO_DEL_DEDUP]
    assert ok is False
    assert "(el motor siempre lo escribe)" in detalle


def test_arithmetic_diario_de_ta_sin_registros_cribados_se_verifica(
    corrida_sin_registros,
) -> None:
    # Sin registros tras el dedup no hay diario de T/A ni qué comprobar.
    ok, _ = _relaciones(corrida_sin_registros)[DIARIO_DENTRO_DEL_DEDUP]
    assert ok is True
