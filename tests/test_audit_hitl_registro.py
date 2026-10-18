"""HITL por registro y decisiones atadas a su solicitud (spec 2026-10-04 §9.3, F2).

``ledger`` (relación 16 y la autonomía efectiva con M5), ``request_hash``
(relación 15), ``hitl`` por registro (L = etiquetas del ledger, H =
``human_label`` de ``decisions.json``, D = ``records`` de ``decision.yml``),
``final_gate`` (relaciones 17 y 18), la rebaja de ``thresholds`` (D7) y la
adjudicación de ``grounding`` (D8).

La corrida real (``corrida``) tiene el T/A aprobado en bloque (A1, D5) y el
texto completo etiquetado registro a registro (A0): 4 etiquetas, una exclusión
humana. Al final, una matriz de corridas reales del motor (``correr_hasta``):
ninguna de las legítimas da un FAIL en estas filas, y las que no lo son sí.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tracemalloc
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import yaml
from audit_fixtures import (
    auditar,
    auditar_en_subproceso,
    bomba_de_alias,
    edit_json,
    edit_ledger,
    edit_yaml,
    escribir_metricas,
    fila,
    metricas_validas,
    write_legacy_v07,
)
from conftest import (
    GOLD_AUDITORIA,
    RAZON_EXCLUSION_FT,
    RAZON_FALSO_POSITIVO,
    adjudicar_auditoria,
    busqueda_auditoria,
    etiquetar_auditoria,
    proveedor_auditoria,
    proveedor_con_cita_marcada,
)
from fakes import ScriptedProvider, fetch_disponible, fetch_no_disponible
from hitl_helpers import correr_hasta, leer_solicitud, responder_gate

from revisia.audit import CHECKS
from revisia.audit.artifacts import AuditContext, load_run
from revisia.audit.checks_hitl import _hash_acotado, autonomia_efectiva_de_la_corrida
from revisia.config import load_protocol
from revisia.llm.registry import ProviderConfig
from revisia.orchestration import pipeline as pipeline_mod
from revisia.orchestration.hitl import HumanDecision, dump_yaml
from revisia.orchestration.pipeline import FetchFn, PipelineResult, run_pipeline
from revisia.orchestration.run_context import RunContext
from revisia.provenance.runmeta import canonical_sha256

TA = "03_screening/decisions.json"
FT = "04_fulltext/decisions.json"
VERIFICATION = "06_synthesis/verification.json"


def _indice(entries: list[dict], stage: str, action: str) -> int:
    return next(i for i, e in enumerate(entries) if (e["stage"], e["action"]) == (stage, action))


def _decision(rid: str, **cambios):
    def _editar(decisions: list[dict]) -> None:
        for decision in decisions:
            if decision["record_id"] == rid:
                decision.update(cambios)

    return _editar


# ── ledger: relación 16 ───────────────────────────────────────────────


def test_ledger_etiqueta_despues_de_su_approve_falla(corrida) -> None:
    def _mover(entries: list[dict]) -> list[dict]:
        label = entries.pop(_indice(entries, "screening_ft", "label"))
        j = _indice(entries, "screening_ft", "approve")
        return [*entries[: j + 1], label, *entries[j + 1 :]]

    edit_ledger(corrida, _mover)
    ledger = fila(auditar(corrida), "ledger")
    assert ledger.status == "FAIL"
    assert "`label` después de su `approve` (relación 16)" in ledger.detail


def test_ledger_etiquetas_con_un_reject_fallan(corrida) -> None:
    def _rechazar(entries: list[dict]) -> None:
        entries[_indice(entries, "screening_ft", "approve")]["action"] = "reject"

    edit_ledger(corrida, _rechazar)
    ledger = fila(auditar(corrida), "ledger")
    assert ledger.status == "FAIL"
    assert "`label` acompaña a un `reject` (relación 16)" in ledger.detail


def test_ledger_tupla_repetida_falla(corrida) -> None:
    def _repetir(entries: list[dict]) -> list[dict]:
        i = _indice(entries, "screening_ft", "label")
        return [*entries[: i + 1], entries[i], *entries[i + 1 :]]

    edit_ledger(corrida, _repetir)
    ledger = fila(auditar(corrida), "ledger")
    assert ledger.status == "FAIL"
    assert "línea 3: repite la tupla de la línea 2 (relación 16)" in ledger.detail


def test_ledger_etiqueta_o_adjudicacion_fuera_de_su_etapa_falla(corrida) -> None:
    # El motor solo escribe `label` en los gates de cribado y `flag_review` en `reporte` (§4.3).
    def _fuera(entries: list[dict]) -> list[dict]:
        i = _indice(entries, "rob", "approve")
        rob = entries[i]
        label = {**rob, "action": "label", "target": "10.1000/llm-1"}
        flag = {**rob, "action": "flag_review", "target": "flag:0"}
        return [*entries[:i], label, flag, *entries[i:]]

    edit_ledger(corrida, _fuera)
    ledger = fila(auditar(corrida), "ledger")
    assert ledger.status == "FAIL"
    assert "`label` en `rob` (solo en los gates de cribado, §4.3)" in ledger.detail
    assert "`flag_review` en `rob` (solo en `reporte`, §4.3)" in ledger.detail


def test_ledger_detalle_hostil_no_revienta_la_relacion_16(corrida) -> None:
    # `detail` es un mapa libre del ledger: un hash que es una lista o un mapa no es hashable.
    def _hostil(entries: list[dict]) -> None:
        for entry in entries:
            if entry["action"] == "label":
                entry["detail"]["decision_sha256"] = {"no": ["es", "un", "hash"]}
                entry["detail"]["request_sha256"] = ["tampoco"]

    edit_ledger(corrida, _hostil)
    report = auditar(corrida)
    assert [c.check_id for c in report.checks if "error interno" in c.detail] == []
    assert fila(report, "hitl").status == "FAIL"  # ya no son etiquetas de la decisión efectiva


# ── ledger: autonomía efectiva (M5) y manifest.autonomy_effective ────


def test_ledger_autonomia_del_manifiesto_distinta_de_la_efectiva_falla(corrida) -> None:
    edit_yaml(corrida / "manifest.yml", lambda m: m["autonomy_effective"].update(rob="A1"))
    ledger = fila(auditar(corrida), "ledger")
    assert ledger.status == "FAIL"
    assert "manifest.autonomy_effective ≠ la efectiva (protocolo + M5) en rob" in ledger.detail


def _sin(clave: str) -> Callable[[dict], None]:
    def _borrar(mapa: dict) -> None:
        del mapa[clave]

    return _borrar


def test_ledger_manifiesto_de_la_ola_1_sin_autonomy_effective_falla(corrida) -> None:
    edit_yaml(corrida / "manifest.yml", _sin("autonomy_effective"))
    ledger = fila(auditar(corrida), "ledger")
    assert ledger.status == "FAIL"
    assert "manifest.yml sin `autonomy_effective`" in ledger.detail


def test_autonomia_efectiva_de_una_corrida_v07_es_la_del_protocolo(tmp_path) -> None:
    ctx = AuditContext(load_run(write_legacy_v07(tmp_path)))
    autonomia = autonomia_efectiva_de_la_corrida(ctx)
    assert autonomia is not None
    assert autonomia["screening_ta"] == "A1"
    assert autonomia["reporte"] == "A1"


# ── request_hash: relación 15 ─────────────────────────────────────────


def test_request_hash_corrida_real_pasa(corrida) -> None:
    request = fila(auditar(corrida), "request_hash")
    assert request.status == "PASS"
    assert request.detail == "5 decisiones humanas atadas a su solicitud (hash recalculado)."


def test_request_hash_solicitud_editada_falla(corrida) -> None:
    edit_yaml(corrida / "screening_ta" / "review_request.yml", lambda r: r.update(n_screened=9))
    request = fila(auditar(corrida), "request_hash")
    assert request.status == "FAIL"
    assert "`screening_ta`: solicitud editada (su request_sha256 no es el de su contenido)" in (
        request.detail
    )


def test_request_hash_solicitud_de_otra_etapa_falla(corrida) -> None:
    # La solicitud de `rob` copiada sobre la de `extraccion`: su hash cuadra con su contenido,
    # pero es la de otra etapa (y la decisión de `extraccion` responde a otra solicitud).
    shutil.copy(corrida / "rob" / "review_request.yml", corrida / "extraccion")
    request = fila(auditar(corrida), "request_hash")
    assert request.status == "FAIL"
    assert "`extraccion`: la solicitud es de otra etapa (rob)" in request.detail


def test_request_hash_valor_que_no_es_json_no_revienta(corrida) -> None:
    # Una fecha YAML sin comillas (`2026-10-04`) se carga como `date`: no es JSON y no se hashea.
    path = corrida / "rob" / "review_request.yml"
    path.write_text(path.read_text(encoding="utf-8") + "fecha: 2026-10-04\n", encoding="utf-8")
    request = fila(auditar(corrida), "request_hash")
    assert request.status == "FAIL"
    assert "`rob`: el contenido de la solicitud no se puede hashear" in request.detail


def test_request_hash_decision_de_otra_solicitud_falla(corrida) -> None:
    def _otra(entries: list[dict]) -> None:
        entries[_indice(entries, "extraccion", "approve")]["detail"]["request_sha256"] = "0" * 64

    edit_ledger(corrida, _otra)
    request = fila(auditar(corrida), "request_hash")
    assert request.status == "FAIL"
    assert "`extraccion`: la decisión efectiva responde a otra solicitud" in request.detail


def test_request_hash_actor_de_decision_yml_distinto_falla(corrida) -> None:
    edit_yaml(corrida / "rob" / "decision.yml", lambda d: d.update(actor="human:otra"))
    request = fila(auditar(corrida), "request_hash")
    assert request.status == "FAIL"
    assert "`rob`: actor de decision.yml (human:otra) ≠ ledger (human:revisora)" in request.detail
    assert "`rob`: decision.yml no es la decisión registrada en el ledger" in request.detail


def test_request_hash_decision_yml_de_otra_solicitud_falla(corrida) -> None:
    edit_yaml(corrida / "rob" / "decision.yml", lambda d: d.update(request_sha256="1" * 64))
    request = fila(auditar(corrida), "request_hash")
    assert request.status == "FAIL"
    assert "`rob`: decision.yml responde a otra solicitud" in request.detail


def test_request_hash_sin_decision_yml_se_reconstruye_del_ledger(corrida) -> None:
    # `decision.yml` es solo el canal de entrada: el motor reanuda aunque se borre (reconstruye
    # la decisión del ledger) y el auditor recalcula el `decision_sha256` del mismo modo.
    (corrida / "rob" / "decision.yml").unlink()
    request = fila(auditar(corrida), "request_hash")
    assert request.status == "PASS"
    assert "decision.yml ausente en `rob`: reconstruida del ledger" in request.detail


def test_request_hash_corrida_real_sin_ningun_decision_yml_sigue_publicable(corrida) -> None:
    # Cinco gates humanos, entre ellos el de texto completo con sus etiquetas por registro: la
    # decisión se reconstruye (records y flags salen de las `label` y `flag_review` del ledger).
    assert auditar(corrida).publishable
    borrados = sorted(corrida.glob("*/decision.yml"))
    assert len(borrados) == 5
    for decision in borrados:
        decision.unlink()
    report = auditar(corrida)
    request = fila(report, "request_hash")
    assert request.status == "PASS", request.detail
    assert "reconstruida del ledger" in request.detail
    assert report.n_fail == 0
    assert report.publishable


def test_request_hash_cita_marcada_sin_decision_yml_reconstruye_las_adjudicaciones(
    corrida_con_cita_marcada,
) -> None:
    (corrida_con_cita_marcada / "reporte" / "decision.yml").unlink()
    report = auditar(corrida_con_cita_marcada)
    assert fila(report, "request_hash").status == "PASS"
    assert report.publishable


def test_request_hash_sin_decision_yml_y_ledger_alterado_advierte(corrida) -> None:
    # Sin el fichero, lo único que se puede recalcular es la decisión que el ledger describe:
    # si el ledger se tocó, ya no es la que se hasheó y el hash no se puede comprobar.
    (corrida / "rob" / "decision.yml").unlink()

    def _tocar(entries: list[dict]) -> None:
        entries[_indice(entries, "rob", "approve")]["detail"]["reason"] = "otra razón"

    edit_ledger(corrida, _tocar)
    request = fila(auditar(corrida), "request_hash")
    assert request.status == "WARN"
    assert "`rob`: decision_sha256 no recalculable sin decision.yml" in request.detail


def test_request_hash_con_decision_yml_presente_el_hash_distinto_sigue_fallando(corrida) -> None:
    edit_yaml(corrida / "rob" / "decision.yml", lambda d: d.update(reason="otra razón"))
    request = fila(auditar(corrida), "request_hash")
    assert request.status == "FAIL"
    assert "`rob`: decision.yml no es la decisión registrada en el ledger" in request.detail


def test_request_hash_decision_yml_con_una_fecha_extra_se_hashea_como_el_motor(corrida) -> None:
    # `HumanDecision` conserva los campos extra y su volcado JSON convierte una fecha YAML sin
    # comillas en texto: el motor hashea esa decisión y escribe la fecha como texto en el ledger.
    # El crudo del fichero no es JSON, pero el auditor hashea lo mismo que el motor.
    path = corrida / "rob" / "decision.yml"
    path.write_text(path.read_text(encoding="utf-8") + "revisada: 2026-10-04\n", encoding="utf-8")
    decision = HumanDecision.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))

    def _registrar(entries: list[dict]) -> None:
        detail = entries[_indice(entries, "rob", "approve")]["detail"]
        detail.update(decision_sha256=canonical_sha256(decision.model_dump(mode="json")))
        detail["revisada"] = "2026-10-04"

    edit_ledger(corrida, _registrar)
    assert fila(auditar(corrida), "request_hash").status == "PASS"
    path.unlink()  # y sin el fichero, el ledger la rehace igual
    request = fila(auditar(corrida), "request_hash")
    assert request.status == "PASS"
    assert "decision.yml ausente en `rob`: reconstruida del ledger" in request.detail


def test_request_hash_sin_decision_yml_de_un_rechazo_real_se_reconstruye(detener_corrida) -> None:
    # Un `reject` no lleva etiquetas: la decisión es `approved: false` con su actor y su razón.
    run = detener_corrida(aprobados=("screening_ta", "screening_ft", "extraccion"), rechazar="rob")
    assert (run / "rob" / "decision.yml").exists()
    (run / "rob" / "decision.yml").unlink()
    request = fila(auditar(run), "request_hash")
    assert request.status != "FAIL", request.detail
    assert "decision.yml ausente en `rob`: reconstruida del ledger" in request.detail


def test_request_hash_sin_decision_yml_con_el_sentido_alterado_advierte(corrida) -> None:
    # La acción del ledger decide `approved`: un `approve` convertido en `reject` ya no es la
    # decisión que se hasheó.
    def _rechazar(entries: list[dict]) -> None:
        entries[_indice(entries, "rob", "approve")]["action"] = "reject"

    edit_ledger(corrida, _rechazar)
    (corrida / "rob" / "decision.yml").unlink()
    request = fila(auditar(corrida), "request_hash")
    assert request.status == "WARN"
    assert "`rob`: decision_sha256 no recalculable sin decision.yml" in request.detail


def test_request_hash_etiqueta_fuera_de_la_solicitud_falla(corrida) -> None:
    def _fuera(entries: list[dict]) -> None:
        entries[_indice(entries, "screening_ft", "label")]["target"] = "10.9999/fantasma"

    edit_ledger(corrida, _fuera)
    request = fila(auditar(corrida), "request_hash")
    assert request.status == "FAIL"
    assert "`screening_ft`: etiquetas fuera de la solicitud: 10.9999/fantasma" in request.detail


def test_request_hash_etiqueta_de_la_decision_efectiva_con_otra_solicitud_falla(corrida) -> None:
    def _otra(entries: list[dict]) -> None:
        entries[_indice(entries, "screening_ft", "label")]["detail"]["request_sha256"] = "2" * 64

    edit_ledger(corrida, _otra)
    request = fila(auditar(corrida), "request_hash")
    assert request.status == "FAIL"
    assert (
        "`screening_ft`: etiquetas o adjudicaciones de la decisión efectiva con otra solicitud: "
        "10.1000/asreview"
    ) in request.detail


def _etiquetas_del_ledger(run: Path, stage: str) -> int:
    """Cuántas ``label`` de ``stage`` hay en el ledger de ``run``."""
    lineas = (run / "decisions_ledger.jsonl").read_text(encoding="utf-8").splitlines()
    return sum(1 for e in map(json.loads, lineas) if (e["stage"], e["action"]) == (stage, "label"))


@pytest.mark.parametrize("declarado", [9, 0, None, True, "4"], ids=repr)
def test_request_hash_n_labels_distinto_de_las_etiquetas_del_ledger_falla(
    corrida, declarado: object
) -> None:
    # El `approve` declara cuántas etiquetas escribió (spec §4.3): contarlas en el ledger delata
    # una etiqueta añadida o borrada a mano, aunque `decisions.json` ya no se pueda contrastar.
    reales = _etiquetas_del_ledger(corrida, "screening_ft")
    assert reales > 0

    def _declarar(entries: list[dict]) -> None:
        detail = entries[_indice(entries, "screening_ft", "approve")]["detail"]
        if declarado is None:
            del detail["n_labels"]
        else:
            detail["n_labels"] = declarado

    edit_ledger(corrida, _declarar)
    request = fila(auditar(corrida), "request_hash")
    assert request.status == "FAIL"
    assert (
        f"`screening_ft`: la decisión declara n_labels={declarado!r} y el ledger tiene "
        f"{reales} etiqueta(s) de esa decisión"
    ) in request.detail


def test_request_hash_etiqueta_borrada_del_ledger_no_cuadra_con_n_labels(corrida) -> None:
    reales = _etiquetas_del_ledger(corrida, "screening_ft")

    def _borrar(entries: list[dict]) -> None:
        del entries[_indice(entries, "screening_ft", "label")]

    edit_ledger(corrida, _borrar)
    request = fila(auditar(corrida), "request_hash")
    assert request.status == "FAIL"
    assert (
        f"`screening_ft`: la decisión declara n_labels={reales} y el ledger tiene {reales - 1} "
        "etiqueta(s) de esa decisión"
    ) in request.detail


def test_request_hash_ids_de_la_solicitud_distintos_de_decisions_json_falla(corrida) -> None:
    # «Un registro cribado disfrazado de duplicado»: falta en decisions.json, sigue en la solicitud.
    def _quitar(decisions: list[dict]) -> None:
        del decisions[-1]

    edit_json(corrida / TA, _quitar)
    request = fila(auditar(corrida), "request_hash")
    assert request.status == "FAIL"
    assert (
        "`screening_ta`: ids de la solicitud ≠ ids de 03_screening/decisions.json: "
        "10.1000/secundario"
    ) in request.detail


@pytest.mark.parametrize(
    ("rel", "gate"),
    [
        ("05_extraction/extractions.json", "extraccion"),
        ("07_rob/assessments.json", "rob"),
        ("deliverable/documento.md", "reporte"),
    ],
)
def test_request_hash_artefacto_aprobado_modificado_falla(corrida, rel: str, gate: str) -> None:
    path = corrida / rel
    if rel.endswith(".json"):
        edit_json(path, lambda data: data.update(añadido={"study_id": "añadido"}))
    else:
        path.write_text(path.read_text(encoding="utf-8") + "\nañadido\n", encoding="utf-8")
    request = fila(auditar(corrida), "request_hash")
    assert request.status == "FAIL"
    assert f"`{gate}`: {rel} no es el " in request.detail


def test_request_hash_must_adjudicate_distinto_de_las_citas_marcadas_falla(
    corrida_con_cita_marcada,
) -> None:
    # La solicitud aprobada pedía adjudicar la cita 1; si verification.json marca además la 0,
    # el humano aprobó otra cosa que lo que hay en disco.
    def _marcar_la_primera(verification: dict) -> None:
        verification["checks"][0]["grounded"] = False

    edit_json(corrida_con_cita_marcada / VERIFICATION, _marcar_la_primera)
    request = fila(auditar(corrida_con_cita_marcada), "request_hash")
    assert request.status == "FAIL"
    assert (
        "`reporte`: must_adjudicate [1] ≠ citas marcadas de 06_synthesis/verification.json [0, 1]"
    ) in request.detail


@pytest.mark.parametrize("fichero", ["review_request.yml", "decision.yml"])
def test_request_hash_bomba_de_alias_no_cuelga_el_auditor(corrida, fichero: str) -> None:
    # Una bomba de alias carga en milisegundos; recorrerla para hashearla (o volcar la decisión)
    # cuelga. El recorrido se acota por el tamaño del fichero: la bomba no es hasheable.
    path = corrida / "rob" / fichero
    path.write_text(bomba_de_alias() + path.read_text(encoding="utf-8"), encoding="utf-8")
    filas = auditar_en_subproceso(corrida, timeout=60)
    estado, detalle = filas["request_hash"]
    assert estado == "FAIL"
    assert "`rob`: " in detalle and "no se puede hashear" in detalle
    assert len(detalle) < 1_500
    assert [i for i, (_, d) in filas.items() if "error interno" in d] == []
    assert len(filas) == len(CHECKS)


# Una bomba de *cadenas*: pocos nodos (el tope por nodos no la ve) y muchos bytes, porque el
# volcado a JSON expande la cadena anclada una vez por cada alias. 24 KB × 2 500 alias = 60 MB.
_RAIZ_DEL_REPO = Path(__file__).resolve().parent.parent
_PICO_MAXIMO = 50 * 2**20  # bytes de memoria que puede asignar una auditoría de una corrida chica
_ALIAS_QUE_SE_EXPANDEN = "estructura YAML con alias que se expanden más allá del tamaño del fichero"
_SCRIPT_MEDIDO = (
    "import json, sys, tracemalloc\n"
    "from revisia.audit import run_audit\n"
    "tracemalloc.start()\n"
    "informe = run_audit(sys.argv[1])\n"
    "pico = tracemalloc.get_traced_memory()[1]\n"
    "filas = [[c.check_id, c.status, c.detail] for c in informe.checks]\n"
    "print(json.dumps({'pico': pico, 'filas': filas}))\n"
)


def _auditar_midiendo(
    corrida: Path, *, timeout: int = 120
) -> tuple[int, dict[str, tuple[str, str]]]:
    """``run_audit`` en un subproceso con ``tracemalloc``: (pico de memoria, filas)."""
    proceso = subprocess.run(
        [sys.executable, "-c", _SCRIPT_MEDIDO, str(corrida)],
        cwd=_RAIZ_DEL_REPO,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    assert proceso.returncode == 0, f"el auditor murió: {proceso.stderr[-500:]}"
    datos = json.loads(proceso.stdout)
    return datos["pico"], {i: (estado, detalle) for i, estado, detalle in datos["filas"]}


def test_auditoria_de_una_corrida_real_cabe_en_el_pico_de_memoria(corrida) -> None:
    # La referencia de los tests siguientes: lo que asigna una auditoría limpia.
    pico, filas = _auditar_midiendo(corrida)
    assert pico < _PICO_MAXIMO // 2, pico
    assert filas["request_hash"][0] == "PASS"


def test_request_hash_bomba_de_cadenas_ancladas_en_la_solicitud_no_agota_la_memoria(
    corrida,
) -> None:
    path = corrida / "rob" / "review_request.yml"
    extra = f'zz_s: &s "{"x" * (24 * 1024)}"\nzz_l: [' + ", ".join(["*s"] * 2_500) + "]\n"
    path.write_text(path.read_text(encoding="utf-8") + extra, encoding="utf-8")
    pico, filas = _auditar_midiendo(corrida)
    estado, detalle = filas["request_hash"]
    assert estado == "FAIL"
    assert (
        f"`rob`: el contenido de la solicitud no se puede hashear ({_ALIAS_QUE_SE_EXPANDEN})"
        in (detalle)
    )
    assert pico < _PICO_MAXIMO, pico
    assert [i for i, (_, d) in filas.items() if "error interno" in d] == []
    assert len(filas) == len(CHECKS)


def test_request_hash_bomba_anidada_de_cadenas_en_la_decision_no_agota_la_memoria(corrida) -> None:
    # `HumanDecision` conserva los campos extra: 8 KB anclados y cuatro niveles de `*b × 9`
    # son 6 561 copias de la cadena (54 MB) en un fichero de 9 KB.
    path = corrida / "rob" / "decision.yml"
    extra = f'zz_s: &b0 "{"x" * (8 * 1024)}"\n' + "".join(
        f"zz_{i}: &b{i} [{', '.join([f'*b{i - 1}'] * 9)}]\n" for i in range(1, 5)
    )
    path.write_text(path.read_text(encoding="utf-8") + extra, encoding="utf-8")
    pico, filas = _auditar_midiendo(corrida)
    estado, detalle = filas["request_hash"]
    assert estado == "FAIL"
    assert f"`rob`: decision.yml no se puede hashear ({_ALIAS_QUE_SE_EXPANDEN})" in detalle
    assert pico < _PICO_MAXIMO, pico
    assert [i for i, (_, d) in filas.items() if "error interno" in d] == []
    assert len(filas) == len(CHECKS)


@pytest.mark.cronometrado
@pytest.mark.parametrize("fichero", ["review_request.yml", "decision.yml"])
def test_request_hash_bomba_de_tuplas_de_pairs_no_agota_la_memoria(corrida, fichero: str) -> None:
    # `!!pairs` (y `!!omap`) construye listas de tuplas, y el JSON canónico las vuelca como
    # arrays: cada alias se expande al hashear. Ocho niveles de nueve alias son 9**8 copias de
    # una cadena de 300 caracteres en un fichero de ~1 KB; el recorrido tiene que cortar antes.
    path = corrida / "rob" / fichero
    niveles = [f'zz_0: &b0 "{"a" * 300}"\n']
    for i in range(1, 9):
        pares = ", ".join(f"{{k: *b{i - 1}}}" for _ in range(9))
        niveles.append(f"zz_{i}: &b{i} !!pairs [{pares}]\n")
    path.write_text(path.read_text(encoding="utf-8") + "".join(niveles), encoding="utf-8")
    try:
        pico, filas = _auditar_midiendo(corrida, timeout=10)
    except subprocess.TimeoutExpired:
        pytest.fail("el auditor no terminó en 10 s: hashear la bomba de !!pairs la expande")
    estado, detalle = filas["request_hash"]
    assert estado == "FAIL"
    assert "`rob`: " in detalle and "no se puede hashear" in detalle
    assert _ALIAS_QUE_SE_EXPANDEN in detalle
    assert pico < _PICO_MAXIMO, pico
    assert [i for i, (_, d) in filas.items() if "error interno" in d] == []
    assert len(filas) == len(CHECKS)


def test_hash_acotado_rechaza_la_expansion_de_cadenas_sin_construirla() -> None:
    cadena = "x" * (32 * 1024)
    valor = {"zz_l": [cadena] * 5_000}  # 5 000 alias de una misma cadena: 160 MB al volcar
    tracemalloc.start()
    try:
        resultado = _hash_acotado(valor, texto="zz_l: [*s, *s]\n")
        pico = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert resultado == (None, _ALIAS_QUE_SE_EXPANDEN)
    assert pico < 5 * 2**20, pico


def test_hash_acotado_cuenta_los_bytes_de_las_claves() -> None:
    clave = "k" * (32 * 1024)
    valor = {"zz_l": [{clave: 1}] * 5_000}  # la clave anclada también se repite al volcar
    assert _hash_acotado(valor, texto="zz_l: [*m, *m]\n") == (None, _ALIAS_QUE_SE_EXPANDEN)


def test_hash_acotado_valor_que_no_es_json_dice_que_no_es_json() -> None:
    assert _hash_acotado({"f": date(2026, 10, 4)}, texto="f: 2026-10-04\n") == (
        None,
        "valores que no son JSON",
    )


def test_hash_acotado_de_los_ficheros_del_motor_es_el_canonico(
    corrida, corrida_con_cita_marcada
) -> None:
    ficheros = [
        path
        for run in (corrida, corrida_con_cita_marcada)
        for patron in ("*/review_request.yml", "*/decision.yml")
        for path in sorted(run.glob(patron))
    ]
    assert len(ficheros) == 20
    for path in ficheros:
        texto = path.read_text(encoding="utf-8")
        valor = yaml.safe_load(texto)
        assert _hash_acotado(valor, texto=texto) == (canonical_sha256(valor), ""), path


def test_hash_acotado_acepta_el_alias_que_escribe_el_motor() -> None:
    # En FT A1 `must_label` y `must_resolve` son la misma lista: `dump_yaml` la ancla y la
    # copia solo duplica su JSON. Aun con miles de ids, el volcado cabe en el tamaño del fichero.
    unclear = [f"10.1000/registro-{n:05d}" for n in range(3_000)]
    texto = dump_yaml({"stage": "screening_ft", "must_label": unclear, "must_resolve": unclear})
    assert "&id001" in texto and "*id001" in texto
    valor = yaml.safe_load(texto)
    assert _hash_acotado(valor, texto=texto) == (canonical_sha256(valor), "")


def test_request_hash_corrida_v07_no_aplica(tmp_path) -> None:
    # Las reglas por registro son del contrato de la Ola 1; una corrida v0.7 se audita por
    # etapa (su FAIL de publicabilidad lo da protocol_snapshot, D13).
    report = auditar(write_legacy_v07(tmp_path))
    assert fila(report, "hitl").status == "PASS"
    request = fila(report, "request_hash")
    assert request.status == "N/A"
    assert "anterior a la Ola 1" in request.detail
    assert fila(report, "protocol_snapshot").status == "FAIL"


def test_request_hash_corrida_en_pausa_ft_verifica_lo_decidido(corrida_en_pausa_ft) -> None:
    report = auditar(corrida_en_pausa_ft)
    request = fila(report, "request_hash")
    assert request.status == "PASS"
    # Lo decidido (T/A) se verifica; el gate pendiente y los que le siguen se anotan como tales.
    assert request.detail == (
        "1 decisión humana atada a su solicitud (hash recalculado). Gates pendientes (no se "
        "evalúan hasta que se decidan de nuevo): `screening_ft`, `extraccion`, `rob`, `reporte`."
    )


# ── hitl por registro ────────────────────────────────────────────────


def test_hitl_human_label_sin_label_en_el_ledger_falla(corrida) -> None:
    def _sin_etiqueta(entries: list[dict]) -> None:
        del entries[_indice(entries, "screening_ft", "label")]

    edit_ledger(corrida, _sin_etiqueta)
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "FAIL"
    assert (
        "`screening_ft`: etiquetas del ledger ≠ human_label de decisions.json: 10.1000/asreview"
    ) in hitl.detail


def test_hitl_label_cambiada_en_decisions_json_falla(corrida) -> None:
    edit_json(
        corrida / FT,
        _decision(
            "10.1000/llm-1", human_label="exclude", human_reason="otra", final_label="exclude"
        ),
    )
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "FAIL"
    assert (
        "`screening_ft`: etiquetas del ledger ≠ human_label de decisions.json: 10.1000/llm-1"
    ) in hitl.detail
    assert "`screening_ft`: razón de la etiqueta ≠ human_reason: 10.1000/llm-1" in hitl.detail


def test_hitl_from_distinto_de_la_propuesta_de_la_ia_falla(corrida) -> None:
    def _from(entries: list[dict]) -> None:
        entries[_indice(entries, "screening_ft", "label")]["detail"]["from"] = "unclear"

    edit_ledger(corrida, _from)
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "FAIL"
    assert "`screening_ft`: `from` ≠ ensemble_label de la IA: 10.1000/asreview" in hitl.detail


def test_hitl_etiqueta_de_otro_actor_que_el_approve_falla(corrida) -> None:
    def _otro(entries: list[dict]) -> None:
        entries[_indice(entries, "screening_ft", "label")]["actor"] = "human:otra"

    edit_ledger(corrida, _otro)
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "FAIL"
    assert (
        "`screening_ft`: etiquetas de otro actor que el del `approve` (human:revisora): "
        "10.1000/asreview"
    ) in hitl.detail


def test_hitl_etiquetas_que_chocan_fallan(corrida) -> None:
    def _choque(entries: list[dict]) -> list[dict]:
        i = _indice(entries, "screening_ft", "label")
        otra = {**entries[i], "detail": {**entries[i]["detail"], "to": "exclude"}}
        return [*entries[: i + 1], otra, *entries[i + 1 :]]

    edit_ledger(corrida, _choque)
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "FAIL"
    assert "`screening_ft`: etiquetas que chocan para 10.1000/asreview" in hitl.detail


def test_hitl_human_actor_distinto_del_approve_falla(corrida) -> None:
    edit_json(corrida / FT, _decision("10.1000/llm-1", human_actor="human:otra"))
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "FAIL"
    assert (
        "`screening_ft`: human_actor ≠ actor del `approve` (human:revisora): 10.1000/llm-1"
    ) in hitl.detail


def test_hitl_decision_yml_distinta_del_ledger_falla(corrida) -> None:
    def _editar(decision: dict) -> None:
        decision["records"]["10.1000/llm-1"] = {"label": "exclude", "reason": "cambio de opinión"}

    edit_yaml(corrida / "screening_ft" / "decision.yml", _editar)
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "FAIL"
    assert "`screening_ft`: etiquetas del ledger ≠ records de decision.yml: 10.1000/llm-1" in (
        hitl.detail
    )


def test_hitl_ft_a0_con_un_recuperado_sin_etiquetar_falla(corrida) -> None:
    edit_ledger(corrida, lambda entries: [e for e in entries if e["target"] != "10.1000/asreview"])
    edit_json(corrida / FT, _decision("10.1000/asreview", human_label=None, human_actor=None))
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "FAIL"
    assert "FT en A0: 1 recuperado(s) sin etiqueta humana: 10.1000/asreview" in hitl.detail


def test_hitl_unclear_sin_resolver_falla(corrida) -> None:
    edit_json(corrida / FT, _decision("10.1000/ensemble", final_label="unclear"))
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "FAIL"
    assert "FT: `unclear` sin resolver por un humano: 10.1000/ensemble" in hitl.detail


def test_hitl_exclusion_humana_ft_sin_razon_falla(corrida) -> None:
    edit_json(corrida / FT, _decision("10.1000/secundario", human_reason=None))
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "FAIL"
    assert "FT: exclusión humana sin razón: 10.1000/secundario" in hitl.detail


def test_hitl_no_recuperado_cribado_por_ia_falla(corrida) -> None:
    edit_json(
        corrida / FT,
        _decision(
            "10.1000/llm-1",
            fulltext_status="not_retrieved",
            votes=[],
            ensemble_label=None,
            human_label=None,
            human_reason=None,
            human_actor=None,
            final_label="include",
        ),
    )
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "FAIL"
    assert "FT: no recuperado(s) con final_label sin rescate humano: 10.1000/llm-1" in hitl.detail


def test_hitl_rescate_sin_razon_falla(corrida) -> None:
    # Un no recuperado con etiqueta humana es un rescate (D2): sin razón no vale.
    edit_json(
        corrida / FT,
        _decision("10.1000/llm-1", fulltext_status="not_retrieved", votes=[], ensemble_label=None),
    )
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "FAIL"
    assert "FT: rescate sin razón: 10.1000/llm-1" in hitl.detail


def test_hitl_ids_hostiles_se_acotan(corrida) -> None:
    enorme = "10.9999/" + "x" * 5_000

    def _muchas(entries: list[dict]) -> list[dict]:
        i = _indice(entries, "screening_ft", "label")
        extra = [{**entries[i], "target": f"{enorme}-{n}"} for n in range(50)]
        return [*entries[:i], *extra, *entries[i:]]

    edit_ledger(corrida, _muchas)
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "FAIL"
    assert enorme not in hitl.detail
    assert "(+47 más)" in hitl.detail
    assert len(hitl.detail) < 2_000


def test_hitl_corrida_v07_sin_etiquetas_se_audita_por_etapa(tmp_path) -> None:
    report = auditar(write_legacy_v07(tmp_path))
    assert fila(report, "hitl").status == "PASS"


# ── final_gate: relaciones 17 y 18 ────────────────────────────────────


def test_final_gate_forced_human_sin_citas_marcadas_falla(corrida) -> None:
    edit_yaml(corrida / "manifest.yml", lambda m: m["final_gate"].update(forced_human=True))
    final_gate = fila(auditar(corrida), "final_gate")
    assert final_gate.status == "FAIL"
    assert (
        "manifest.final_gate.forced_human=True y hallucination_flagged=False (relación 17)"
    ) in final_gate.detail


def test_final_gate_manifiesto_sin_final_gate_falla(corrida) -> None:
    edit_yaml(corrida / "manifest.yml", _sin("final_gate"))
    final_gate = fila(auditar(corrida), "final_gate")
    assert final_gate.status == "FAIL"
    assert "manifest.yml sin `final_gate`" in final_gate.detail


def test_final_gate_cita_marcada_sin_forzar_el_gate_falla(corrida_con_cita_marcada) -> None:
    def _sin_forzar(entries: list[dict]) -> None:
        entries[_indice(entries, "reporte", "approve")]["detail"]["forced_human"] = False

    edit_ledger(corrida_con_cita_marcada, _sin_forzar)
    final_gate = fila(auditar(corrida_con_cita_marcada), "final_gate")
    assert final_gate.status == "FAIL"
    assert (
        "la decisión final no se forzó a humana (forced_human=False) y hallucination_flagged=True"
    ) in final_gate.detail


@pytest.mark.parametrize(
    ("cambio", "motivo"),
    [
        pytest.param({"actor": "human:otra"}, "otro actor", id="otro-actor"),
        pytest.param({"actor": "agent:verificador"}, "no humana", id="agente"),
    ],
)
def test_final_gate_flag_review_de_otro_actor_falla(
    corrida_con_cita_marcada, cambio: dict, motivo: str
) -> None:
    def _cambiar(entries: list[dict]) -> None:
        entries[_indice(entries, "reporte", "flag_review")].update(cambio)

    edit_ledger(corrida_con_cita_marcada, _cambiar)
    report = auditar(corrida_con_cita_marcada)
    final_gate = fila(report, "final_gate")
    assert final_gate.status == "FAIL", motivo
    assert (
        "citas marcadas [1] sin `flag_review` de human:revisora en ese `approve` (relación 17)"
    ) in final_gate.detail
    assert not report.publishable


def test_final_gate_run_json_completed_sin_aprobar_el_reporte_falla(corrida) -> None:
    def _rechazar(entries: list[dict]) -> None:
        entries[_indice(entries, "reporte", "approve")]["action"] = "reject"

    edit_ledger(corrida, _rechazar)
    final_gate = fila(auditar(corrida), "final_gate")
    assert final_gate.status == "FAIL"
    assert "run.json dice `completed` sin un `approve` del reporte (relación 18)" in (
        final_gate.detail
    )


@pytest.mark.parametrize(
    ("estado", "etapa", "esperado"),
    [
        pytest.param(
            "paused",
            "screening_ft",
            "corrida en pausa en `screening_ft`: sin decisión final",
            id="paused",
        ),
        pytest.param(
            "interrupted",
            "extraccion",
            "corrida interrumpida en `extraccion`: sin decisión final",
            id="interrupted",
        ),
        pytest.param(
            "running",
            "rob",
            "run.json dice `running` en `rob`: la corrida no terminó",
            id="running",
        ),
    ],
)
def test_final_gate_run_json_sin_terminar_con_el_reporte_aprobado_falla(
    corrida, estado: str, etapa: str, esperado: str
) -> None:
    # El `approve` del reporte puede ser de una vuelta anterior: si `run.json` dice que la corrida
    # no terminó (pausada, interrumpida o con el proceso muerto), no hay decisión final.
    path = corrida / "run.json"
    info = json.loads(path.read_text(encoding="utf-8"))
    info.update(status=estado, stage=etapa)
    path.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    report = auditar(corrida)
    final_gate = fila(report, "final_gate")
    assert final_gate.status == "FAIL"
    # En pausa o interrumpida, ese es el estado aunque el ledger conserve el `approve` del
    # reporte (revisión final de la Ola 1, E2a); `running` sigue siendo «no terminó».
    assert esperado in final_gate.detail
    assert not report.publishable


def test_final_gate_aprobacion_del_reporte_de_otra_solicitud_falla(corrida) -> None:
    # Un `approve` cuyo `request_sha256` no es el de la `review_request.yml` de ahora no es la
    # decisión final efectiva: es de una solicitud que ya no existe.
    def _otra(entries: list[dict]) -> None:
        entries[_indice(entries, "reporte", "approve")]["detail"]["request_sha256"] = "0" * 64

    edit_ledger(corrida, _otra)
    report = auditar(corrida)
    final_gate = fila(report, "final_gate")
    assert final_gate.status == "FAIL"
    assert "responde a otra solicitud que la vigente" in final_gate.detail
    assert not report.publishable


def test_final_gate_corrida_completada_y_reanudada_sigue_publicable(
    corrida, protocolo_auditoria: Path, tmp_path: Path
) -> None:
    # Reanudar una corrida terminada pasa por `running` y vuelve a `completed`; el ledger no
    # cambia y el reporte sigue aprobado: no es una corrida sin terminar.
    _, result = _correr(corrida, tmp_path, protocolo_auditoria)
    assert result.status == "completed", result.message
    assert json.loads((corrida / "run.json").read_text(encoding="utf-8"))["status"] == "completed"
    report = auditar(corrida)
    assert fila(report, "final_gate").status == "PASS"
    assert report.n_fail == 0
    assert report.publishable


def test_final_gate_reinclusion_tras_completar_deja_la_corrida_sin_terminar(
    corrida, protocolo_auditoria: Path, tmp_path: Path
) -> None:
    # Caso real: completada la corrida, la revisora reincluye un registro en T/A y reanuda; la
    # corrida se detiene en texto completo (otra solicitud) con el `approve` viejo del reporte
    # todavía en el ledger. `final_gate` no puede dar PASS: `run.json` dice `paused`.
    solicitud = leer_solicitud(corrida, "screening_ta")
    reincluido = (
        "10.1000/cocina"
        if "10.1000/cocina" in solicitud["ai_excluded"]
        else (solicitud["ai_excluded"][0])
    )
    responder_gate(
        corrida,
        "screening_ta",
        records={reincluido: {"label": "include", "reason": "relevante: habla de cribado"}},
    )
    _, result = _correr(corrida, tmp_path, protocolo_auditoria, parar_en="screening_ft")
    assert result.status == "paused", result.message
    report = auditar(corrida)
    # E2a: el estado es la pausa en texto completo, no `completed` por el `approve` viejo.
    assert report.state is not None
    assert (report.state.status, report.state.pending_stage) == ("paused", "screening_ft")
    final_gate = fila(report, "final_gate")
    assert final_gate.status == "FAIL"
    assert "corrida en pausa en `screening_ft`: sin decisión final" in final_gate.detail
    assert not report.publishable


def test_reinclusion_d14_tras_completar_no_juzga_las_decisiones_sustituidas_del_gate_pendiente(
    corrida, protocolo_auditoria: Path, tmp_path: Path
) -> None:
    # Misma corrida: la reinclusión D14 sustituye la decisión de `screening_ft` y la reabre. Hasta
    # que la revisora responda, el ledger conserva la decisión SUSTITUIDA de ese gate (y las de los
    # posteriores) frente a artefactos ya rehechos: `hitl` («FT en A0: … sin etiqueta humana») y
    # `request_hash` («responde a otra solicitud») juzgaban lo que ya no vale. Los gates
    # pendientes se anotan como tales y no se evalúan; `final_gate` sigue dando el FAIL.
    solicitud = leer_solicitud(corrida, "screening_ta")
    reincluido = (
        "10.1000/cocina"
        if "10.1000/cocina" in solicitud["ai_excluded"]
        else (solicitud["ai_excluded"][0])
    )
    responder_gate(
        corrida,
        "screening_ta",
        records={reincluido: {"label": "include", "reason": "relevante: habla de cribado"}},
    )
    _, result = _correr(corrida, tmp_path, protocolo_auditoria, parar_en="screening_ft")
    assert result.status == "paused", result.message

    report = auditar(corrida)

    assert report.state is not None
    assert (report.state.status, report.state.pending_stage) == ("paused", "screening_ft")
    hitl, request_hash = fila(report, "hitl"), fila(report, "request_hash")
    assert hitl.status != "FAIL", hitl.detail
    assert request_hash.status != "FAIL", request_hash.detail
    for row in (hitl, request_hash):
        assert "pendientes" in row.detail and "`screening_ft`" in row.detail
        assert "sin etiqueta humana" not in row.detail
        assert "responde a otra solicitud" not in row.detail
    assert fila(report, "final_gate").status == "FAIL"
    assert not report.publishable


# ── thresholds (D7) y grounding (D8) con etiquetas humanas ───────────


def _etiquetar_exclusiones_ia(
    run: Path,
    *,
    solo: tuple[str, ...] | None = None,
    en_el_ledger: bool = True,
    decision_sha256: str | None = None,
    actor: str | None = None,
) -> list[str]:
    """La revisora etiqueta en T/A las exclusiones de la IA (``solo``: algunas) como las escribe
    el motor: ``human_label`` en ``decisions.json`` y, con ``en_el_ledger``, una ``label`` por
    registro antes del ``approve`` (``decision_sha256`` y ``actor`` fuerzan una etiqueta ajena)."""
    ids: list[str] = []

    def _en_decisions(decisions: list[dict]) -> None:
        for decision in decisions:
            if decision["ensemble_label"] == "exclude" and (
                solo is None or decision["record_id"] in solo
            ):
                decision.update(
                    human_label="exclude",
                    human_reason="revisada a mano",
                    human_actor="human:revisora",
                )
                ids.append(decision["record_id"])

    edit_json(run / TA, _en_decisions)
    if not en_el_ledger:
        return ids

    def _en_el_ledger(entries: list[dict]) -> list[dict]:
        i = _indice(entries, "screening_ta", "approve")
        aprobacion = entries[i]
        hashes = {k: aprobacion["detail"][k] for k in ("request_sha256", "decision_sha256")}
        if decision_sha256 is not None:
            hashes["decision_sha256"] = decision_sha256
        etiquetas = [
            {
                **aprobacion,
                "actor": actor or aprobacion["actor"],
                "action": "label",
                "target": rid,
                "detail": {
                    "from": "exclude",
                    "to": "exclude",
                    "reason": "revisada a mano",
                    "rescue": False,
                    **hashes,
                },
            }
            for rid in ids
        ]
        aprobacion["detail"]["n_labels"] = len(ids)
        return [*entries[:i], *etiquetas, *entries[i:]]

    edit_ledger(run, _en_el_ledger)
    return ids


def test_thresholds_recall_bajo_con_todas_las_exclusiones_ia_etiquetadas_advierte(corrida) -> None:
    _etiquetar_exclusiones_ia(corrida)
    escribir_metricas(corrida, metricas_validas(18, 0, 2, 10))
    thresholds = fila(auditar(corrida), "thresholds")
    assert thresholds.status == "WARN"
    assert (
        "recall 0.90 [IC95 0.70–0.97] < 0.95 con 20 positivos, pero todas las exclusiones IA de "
        "T/A tienen etiqueta humana: decláralo (D7)"
    ) in thresholds.detail


def test_thresholds_recall_bajo_con_una_exclusion_ia_sin_etiquetar_sigue_fallando(corrida) -> None:
    _etiquetar_exclusiones_ia(corrida, solo=("10.1000/cocina",))
    escribir_metricas(corrida, metricas_validas(18, 0, 2, 10))
    thresholds = fila(auditar(corrida), "thresholds")
    assert thresholds.status == "FAIL"
    assert "1 exclusiones IA de T/A sin etiqueta humana" in thresholds.detail


def test_thresholds_human_label_solo_en_decisions_json_no_rebaja_el_recall(corrida) -> None:
    # `decisions.json` es una copia: una `human_label` sin su `label` en el ledger no la puso
    # nadie. Antes `thresholds` daba WARN y `hitl` FAIL sobre el mismo hecho; ahora coinciden.
    _etiquetar_exclusiones_ia(corrida, en_el_ledger=False)
    escribir_metricas(corrida, metricas_validas(18, 0, 2, 10))
    report = auditar(corrida)
    thresholds = fila(report, "thresholds")
    assert thresholds.status == "FAIL"
    assert "2 exclusiones IA de T/A sin etiqueta humana" in thresholds.detail
    assert fila(report, "hitl").status == "FAIL"
    assert not report.publishable


@pytest.mark.parametrize(
    ("cambio", "motivo"),
    [
        pytest.param({"decision_sha256": "a" * 64}, "de otra decisión", id="otra-decision"),
        pytest.param({"actor": "agent:cribador"}, "no humana", id="agente"),
    ],
)
def test_thresholds_etiquetas_que_no_son_humanas_de_la_decision_efectiva_no_cuentan(
    corrida, cambio: dict, motivo: str
) -> None:
    _etiquetar_exclusiones_ia(corrida, **cambio)
    escribir_metricas(corrida, metricas_validas(18, 0, 2, 10))
    thresholds = fila(auditar(corrida), "thresholds")
    assert thresholds.status == "FAIL", motivo
    assert "2 exclusiones IA de T/A sin etiqueta humana" in thresholds.detail


def test_grounding_marca_real_adjudicada_por_la_revisora_advierte(
    corrida_con_cita_marcada,
) -> None:
    # Corrida real: la síntesis cita [2019], que no está en el corpus; el gate final se fuerza
    # a humano y la revisora la adjudica como falso positivo.
    report = auditar(corrida_con_cita_marcada)
    grounding = fila(report, "grounding")
    assert grounding.status == "WARN"
    assert grounding.detail == (
        "1 citas marcadas, adjudicadas como falsos positivos por human:revisora: decláralo."
    )
    assert fila(report, "final_gate").status == "PASS"
    assert fila(report, "request_hash").status == "PASS"
    assert report.n_fail == 0
    assert report.publishable
    ledger = (corrida_con_cita_marcada / "decisions_ledger.jsonl").read_text(encoding="utf-8")
    revisiones = [e for e in map(json.loads, ledger.splitlines()) if e["action"] == "flag_review"]
    assert [(r["target"], r["detail"]["reason"]) for r in revisiones] == [
        ("flag:1", RAZON_FALSO_POSITIVO)
    ]


def test_grounding_marca_real_sin_su_adjudicacion_falla(corrida_con_cita_marcada) -> None:
    edit_ledger(
        corrida_con_cita_marcada, lambda es: [e for e in es if e["action"] != "flag_review"]
    )
    report = auditar(corrida_con_cita_marcada)
    grounding = fila(report, "grounding")
    assert grounding.status == "FAIL"
    assert "1 cita(s) marcada(s) sin adjudicar por un humano (D8): índices [1]" in (
        grounding.detail
    )
    assert "citas marcadas [1] sin `flag_review`" in fila(report, "final_gate").detail


# ── Corridas reales del motor (la matriz del informe de la Tarea 15) ──
#
# Cada escenario es una corrida real (`correr_hasta`, `responder_gate`): la revisora decide en
# cada pausa. Ninguna corrida legítima da FAIL en `ledger`, `hitl`, `request_hash` ni
# `final_gate`; `--auto-approve` sigue sin ser publicable (D8).

RAZON_RESCATE = "PDF conseguido por correo con la autora"
RAZON_EXCEPCION = "el resumen sí habla de cribado"
SIN_TEXTO = ("10.1000/asreview",)


def _protocolo(base: Path, origen: Path, **cambios: object) -> Path:
    """Copia del protocolo de la auditoría con claves de ``protocol.yml`` cambiadas."""
    destino = base / "protocolo" / origen.name
    shutil.copytree(origen, destino)
    path = destino / "protocol.yml"
    crudo = yaml.safe_load(path.read_text(encoding="utf-8"))
    for clave, valor in cambios.items():
        if clave == "autonomy_reporte":
            crudo["autonomy"]["reporte"] = valor
        elif clave == "gold":
            (destino / "gold.yml").write_text(yaml.safe_dump({"gold": valor}), encoding="utf-8")
        else:
            crudo[clave] = valor
    path.write_text(yaml.safe_dump(crudo, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return destino


def _correr(
    run_dir: Path | None,
    base: Path,
    protocolo: Path,
    *,
    etiquetar: Callable[[str, dict], dict | None] = etiquetar_auditoria,
    proveedor: Callable[[ProviderConfig], ScriptedProvider] = proveedor_auditoria,
    fetch: FetchFn = fetch_disponible,
    parar_en: str | None = None,
    auto_approve: bool = False,
) -> tuple[Path, PipelineResult]:
    """Corre (o, con ``run_dir``, reanuda) el pipeline real; la revisora es ``etiquetar``."""
    protocol = load_protocol(protocolo)
    if run_dir is None:
        ctx = RunContext(protocol.slug, base / "runs", datetime.now(UTC).strftime("%Y%m%d-%H%M%S"))
    else:
        ctx = RunContext.open(run_dir)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pipeline_mod, "build_provider", proveedor)
        if auto_approve:
            result = run_pipeline(
                protocol,
                protocolo,
                ctx,
                auto_approve=True,
                search_fn=busqueda_auditoria,
                fetch_fn=fetch,
            )
        else:
            result = correr_hasta(
                protocol,
                protocolo,
                ctx,
                search_fn=busqueda_auditoria,
                fetch_fn=fetch,
                etiquetar=etiquetar,
                parar_en=parar_en,
            )
    return ctx.run_dir, result


def _con_excepcion_en_ta(stage: str, solicitud: dict) -> dict | None:
    """T/A aprobado en bloque con una excepción: «botánica» pasa a texto completo."""
    if stage == "screening_ta":
        return {"records": {"10.1000/botanica": {"label": "include", "reason": RAZON_EXCEPCION}}}
    return etiquetar_auditoria(stage, solicitud)


def _rescatar(stage: str, solicitud: dict) -> dict | None:
    """Etiqueta los recuperados (A0) y rescata los no recuperados, con razón (D2)."""
    extra = etiquetar_auditoria(stage, solicitud)
    if stage != "screening_ft":
        return extra
    records = dict((extra or {}).get("records", {}))
    for record_id in solicitud.get("rescuable", []):
        records[record_id] = {"label": "include", "reason": RAZON_RESCATE}
    return {"records": records}


def _todas_las_exclusiones_ia(run_dir: Path) -> dict:
    """``records`` de T/A que etiqueta cada exclusión de la IA (lo que pide D7)."""
    solicitud = leer_solicitud(run_dir, "screening_ta")
    return {
        rid: {"label": "exclude", "reason": "revisada a mano: fuera de alcance"}
        for rid in solicitud["ai_excluded"]
    }


def _humana_a1_con_excepcion(base: Path, protocolo: Path) -> Path:
    return _correr(None, base, protocolo, etiquetar=_con_excepcion_en_ta)[0]


def _ft_a0_etiquetado(base: Path, protocolo: Path) -> Path:
    return _correr(None, base, protocolo)[0]


def _rescates(base: Path, protocolo: Path) -> Path:
    fetch = fetch_no_disponible(SIN_TEXTO)
    return _correr(None, base, protocolo, etiquetar=_rescatar, fetch=fetch)[0]


def _rechazo_y_reetiquetado(base: Path, protocolo: Path) -> Path:
    # D14: la revisora rechaza el texto completo; luego cambia de opinión, etiqueta y reanuda.
    def _rechazar(stage: str, solicitud: dict) -> dict | None:
        if stage == "screening_ft":
            return {"approved": False, "reason": "falta revisar los textos"}
        return etiquetar_auditoria(stage, solicitud)

    run_dir, result = _correr(None, base, protocolo, etiquetar=_rechazar)
    assert result.status == "rejected", result.message
    extra = etiquetar_auditoria("screening_ft", leer_solicitud(run_dir, "screening_ft"))
    responder_gate(run_dir, "screening_ft", reason="revisados los textos", **(extra or {}))
    return _correr(run_dir, base, protocolo)[0]


def _reetiquetado_d7(base: Path, protocolo: Path) -> Path:
    # Recall bajo (`cocina` es relevante para el gold y la IA la excluye): la revisora etiqueta
    # todas las exclusiones de la IA en `screening_ta/decision.yml` y reanuda (D7, D14).
    proto = _protocolo(base, protocolo, gold={**GOLD_AUDITORIA, "10.1000/cocina": True})
    run_dir, _ = _correr(None, base, proto)
    shutil.copytree(run_dir, base / "antes" / run_dir.name)
    responder_gate(run_dir, "screening_ta", records=_todas_las_exclusiones_ia(run_dir))
    return _correr(run_dir, base, proto)[0]


def _reinclusion_d14(base: Path, protocolo: Path) -> Path:
    # Como `_reetiquetado_d7`, pero la revisora rescata en T/A la exclusión que el gold dice
    # relevante: cambia lo que pasa a texto completo, las solicitudes de los gates siguientes
    # cambian y las decisiones anteriores de esos gates quedan sustituidas (D14). Todas las
    # decisiones efectivas acaban atadas a las solicitudes vigentes.
    proto = _protocolo(base, protocolo, gold={**GOLD_AUDITORIA, "10.1000/cocina": True})
    run_dir, _ = _correr(None, base, proto)
    records = _todas_las_exclusiones_ia(run_dir)
    records["10.1000/cocina"] = {"label": "include", "reason": "relevante: habla de cribado"}
    responder_gate(run_dir, "screening_ta", records=records)
    return _correr(run_dir, base, proto)[0]


def _cita_marcada_a1(base: Path, protocolo: Path) -> Path:
    proto = _protocolo(base, protocolo, grounding="existence")
    etiquetar, proveedor = adjudicar_auditoria, proveedor_con_cita_marcada
    return _correr(None, base, proto, etiquetar=etiquetar, proveedor=proveedor)[0]


def _cita_marcada_a2_forzada(base: Path, protocolo: Path) -> Path:
    # `reporte` declarado A2: con la cita marcada el motor lo fuerza a A1 (M5).
    proto = _protocolo(base, protocolo, grounding="existence", autonomy_reporte="A2")
    etiquetar, proveedor = adjudicar_auditoria, proveedor_con_cita_marcada
    return _correr(None, base, proto, etiquetar=etiquetar, proveedor=proveedor)[0]


def _auto_approve(base: Path, protocolo: Path) -> Path:
    return _correr(None, base, protocolo, auto_approve=True)[0]


def _en_pausa_ft(base: Path, protocolo: Path) -> Path:
    return _correr(None, base, protocolo, parar_en="screening_ft")[0]


ESCENARIOS: dict[str, Callable[[Path, Path], Path]] = {
    "humana-a1-con-excepcion": _humana_a1_con_excepcion,
    "ft-a0-etiquetado": _ft_a0_etiquetado,
    "rescates": _rescates,
    "rechazo-y-reetiquetado": _rechazo_y_reetiquetado,
    "reetiquetado-d7": _reetiquetado_d7,
    "reinclusion-d14": _reinclusion_d14,
    "cita-marcada-a1": _cita_marcada_a1,
    "cita-marcada-a2-forzada": _cita_marcada_a2_forzada,
    "auto-approve": _auto_approve,
    "en-pausa-ft": _en_pausa_ft,
}

_FILAS = ("ledger", "hitl", "request_hash", "final_gate", "grounding", "thresholds")
_OK = {"ledger": "PASS", "hitl": "PASS", "request_hash": "PASS", "final_gate": "PASS"}
# Estado esperado de cada fila (las que no se nombran: PASS o WARN) y si es publicable.
ESPERADO: dict[str, tuple[dict[str, str], bool]] = {
    "humana-a1-con-excepcion": (_OK, True),
    "ft-a0-etiquetado": (_OK, True),
    "rescates": (_OK, True),
    "rechazo-y-reetiquetado": (_OK, True),
    "reetiquetado-d7": ({**_OK, "thresholds": "WARN"}, True),
    "reinclusion-d14": ({**_OK, "thresholds": "WARN"}, True),
    "cita-marcada-a1": ({**_OK, "grounding": "WARN"}, True),
    "cita-marcada-a2-forzada": ({**_OK, "grounding": "WARN"}, True),
    "auto-approve": (
        {"ledger": "PASS", "hitl": "FAIL", "request_hash": "PASS", "final_gate": "FAIL"},
        False,
    ),
    "en-pausa-ft": ({**_OK, "final_gate": "FAIL", "grounding": "N/A"}, False),
}


@pytest.fixture(scope="module")
def escenario(
    tmp_path_factory: pytest.TempPathFactory, protocolo_auditoria: Path
) -> Callable[[str], Path]:
    """Corridas reales de ``ESCENARIOS``, generadas una vez por módulo (no se editan)."""
    cache: dict[str, Path] = {}

    def _obtener(nombre: str) -> Path:
        if nombre not in cache:
            cache[nombre] = ESCENARIOS[nombre](tmp_path_factory.mktemp(nombre), protocolo_auditoria)
        return cache[nombre]

    return _obtener


@pytest.mark.parametrize("nombre", list(ESCENARIOS))
def test_corridas_reales_sin_fail_falso_en_la_supervision_humana(escenario, nombre: str) -> None:
    report = auditar(escenario(nombre))
    esperado, publicable = ESPERADO[nombre]
    estados = {f: fila(report, f).status for f in _FILAS}
    for check_id, estado in esperado.items():
        assert estados[check_id] == estado, (check_id, fila(report, check_id).detail)
    for check_id in set(_FILAS) - set(esperado):
        assert estados[check_id] in ("PASS", "WARN"), (check_id, fila(report, check_id).detail)
    assert [c.check_id for c in report.checks if "error interno" in c.detail] == []
    assert report.publishable is publicable, [
        (c.check_id, c.detail) for c in report.checks if c.status == "FAIL"
    ]


def _desde_la_plantilla(stage: str, solicitud: dict) -> dict | None:
    """La revisora rellena ``decision.template.yml`` y deja el resto de las entradas en ``null``.

    La plantilla lista cada registro como ``{label: null, reason: null}``: quien solo etiqueta
    unos pocos guarda el fichero con todas las demás entradas sin etiquetar, y el motor hashea
    esa decisión entera (``records`` incluye los ``null``).
    """
    etiquetas = (_con_excepcion_en_ta(stage, solicitud) or {}).get("records", {})
    if stage not in ("screening_ta", "screening_ft"):
        return _con_excepcion_en_ta(stage, solicitud)
    sin_etiquetar = {r["record_id"]: {"label": None, "reason": None} for r in solicitud["records"]}
    return {"records": {**sin_etiquetar, **etiquetas}}


def test_request_hash_sin_decision_yml_rehace_tambien_las_entradas_de_la_plantilla_sin_etiquetar(
    tmp_path, protocolo_auditoria: Path
) -> None:
    run, _ = _correr(None, tmp_path, protocolo_auditoria, etiquetar=_desde_la_plantilla)
    decisiones = sorted(run.glob("*/decision.yml"))
    assert len(decisiones) == 5
    crudo = yaml.safe_load((run / "screening_ta" / "decision.yml").read_text(encoding="utf-8"))
    assert any(r["label"] is None for r in crudo["records"].values())  # la plantilla con nulls
    assert fila(auditar(run), "request_hash").status == "PASS"
    for decision in decisiones:
        decision.unlink()
    report = auditar(run)
    request = fila(report, "request_hash")
    assert request.status == "PASS", request.detail
    assert "decision.yml ausente en `screening_ta`, `screening_ft`" in request.detail
    assert report.publishable


def test_corrida_con_excepcion_en_ta_registra_la_etiqueta(escenario) -> None:
    run = escenario("humana-a1-con-excepcion")
    hitl = fila(auditar(run), "hitl")
    # 1 excepción en T/A + 5 recuperados etiquetados en FT (botánica pasó y la IA la excluye).
    assert "6 etiqueta(s) por registro" in hitl.detail


def test_corrida_rescatada_lleva_su_razon(escenario) -> None:
    run = escenario("rescates")
    ft = {d["record_id"]: d for d in json.loads((run / FT).read_text(encoding="utf-8"))}
    assert ft["10.1000/asreview"]["fulltext_status"] == "not_retrieved"
    assert ft["10.1000/asreview"]["human_reason"] == RAZON_RESCATE


def test_corrida_d7_antes_de_reetiquetar_falla_y_despues_advierte(escenario) -> None:
    run = escenario("reetiquetado-d7")
    antes = auditar(run.parent.parent / "antes" / run.name)
    assert fila(antes, "thresholds").status == "FAIL"
    assert "2 exclusiones IA de T/A sin etiqueta humana" in fila(antes, "thresholds").detail
    despues = fila(auditar(run), "thresholds")
    assert "todas las exclusiones IA de T/A tienen etiqueta humana: decláralo (D7)" in (
        despues.detail
    )


def test_corrida_reincluida_sustituye_la_decision_de_texto_completo(escenario) -> None:
    run = escenario("reinclusion-d14")
    ledger = (run / "decisions_ledger.jsonl").read_text(encoding="utf-8")
    aprobados = [
        e["stage"] for e in map(json.loads, ledger.splitlines()) if e["action"] == "approve"
    ]
    assert aprobados.count("screening_ta") == 2
    assert aprobados.count("screening_ft") == 2  # la solicitud de FT cambió: se volvió a decidir
    ft = {d["record_id"]: d for d in json.loads((run / FT).read_text(encoding="utf-8"))}
    assert ft["10.1000/cocina"]["human_label"] is not None


def test_corrida_a2_forzada_registra_a1_en_el_ledger_y_el_manifiesto(escenario) -> None:
    run = escenario("cita-marcada-a2-forzada")
    manifest = yaml.safe_load((run / "manifest.yml").read_text(encoding="utf-8"))
    assert manifest["autonomy_effective"]["reporte"] == "A1"
    assert manifest["final_gate"]["forced_human"] is True
    autonomia = autonomia_efectiva_de_la_corrida(AuditContext(load_run(run)))
    assert autonomia is not None and autonomia["reporte"] == "A1"


def test_corrida_auto_approve_no_es_publicable_y_dice_por_que(escenario) -> None:
    report = auditar(escenario("auto-approve"))
    assert "D8: --auto-approve no es revisión humana" in fila(report, "hitl").detail
    request = fila(report, "request_hash")
    assert request.status == "PASS"
    assert "5 no humanas: ver `hitl`" in request.detail


def test_corrida_rechazada_y_reetiquetada_conserva_el_rechazo(escenario) -> None:
    run = escenario("rechazo-y-reetiquetado")
    ledger = (run / "decisions_ledger.jsonl").read_text(encoding="utf-8")
    acciones = [
        e["action"]
        for e in map(json.loads, ledger.splitlines())
        if e["stage"] == "screening_ft" and e["action"] in ("approve", "reject")
    ]
    assert acciones == ["reject", "approve"]


def test_corrida_texto_completo_etiquetado_razon_de_exclusion(escenario) -> None:
    run = escenario("ft-a0-etiquetado")
    ft = {d["record_id"]: d for d in json.loads((run / FT).read_text(encoding="utf-8"))}
    assert ft["10.1000/secundario"]["human_reason"] == RAZON_EXCLUSION_FT
