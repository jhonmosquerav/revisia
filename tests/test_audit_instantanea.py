"""Artefactos de la Ola 1: ``protocol_snapshot`` (D13), esquemas, etapas y lista 16b.

Spec 2026-10-04 §9.3 (filas 3, 4, 11, 14 y 20) y §9.4 (familias
``protocol_snapshot``, ``schemas`` y ``deliverable``, F2).
"""

from __future__ import annotations

import json
import shutil

import pytest
from audit_fixtures import (
    auditar,
    auditar_en_subproceso,
    bomba_de_alias,
    edit_json,
    edit_yaml,
    editar_llamadas,
    editar_protocolo,
    fila,
    write_legacy_v07,
)

from revisia.audit import CHECKS
from revisia.audit.artifacts import JSONL_ADAPTERS, AuditContext, load_run
from revisia.audit.checks_provenance import LEGACY_RUN
from revisia.orchestration.snapshot import protocol_fingerprint

# ── protocol_snapshot ─────────────────────────────────────────────────


def test_protocol_snapshot_corrida_real_pasa(corrida) -> None:
    snapshot = fila(auditar(corrida), "protocol_snapshot")
    assert snapshot.status == "PASS"
    assert "6 ficheros de 00_protocol/ con el hash de run.json" in snapshot.detail


def test_protocol_snapshot_corrida_anterior_a_la_ola_1_falla_pero_se_diagnostica(tmp_path) -> None:
    # D13: no publicable, pero auditable como diagnóstico con las relaciones v0.7.
    report = auditar(write_legacy_v07(tmp_path))
    snapshot = fila(report, "protocol_snapshot")
    assert snapshot.status == "FAIL"
    assert snapshot.detail == (
        "anterior a la Ola 1 (motor < 0.8): sin instantánea ni decisiones por registro; "
        "regenera la corrida con el motor actual."
    )
    assert snapshot.detail == f"{LEGACY_RUN}."
    assert fila(report, "arithmetic").status == "PASS"
    assert "relaciones v0.7" in fila(report, "arithmetic").detail
    assert fila(report, "schemas").status == "PASS"  # sus decision.yml son de v0.7
    assert not report.publishable


def test_protocol_snapshot_hash_alterado_falla(corrida) -> None:
    path = corrida / "00_protocol" / "inclusion_exclusion.yml"
    path.write_text(path.read_text(encoding="utf-8") + "# editado a mano\n", encoding="utf-8")
    snapshot = fila(auditar(corrida), "protocol_snapshot")
    assert snapshot.status == "FAIL"
    assert "`00_protocol/inclusion_exclusion.yml`: hash distinto del de run.json" in (
        snapshot.detail
    )


def test_protocol_snapshot_fichero_de_la_lista_ausente_falla(corrida) -> None:
    (corrida / "00_protocol" / "effects.yml").unlink()
    snapshot = fila(auditar(corrida), "protocol_snapshot")
    assert snapshot.status == "FAIL"
    assert "`00_protocol/effects.yml` ausente" in snapshot.detail


def test_protocol_snapshot_instantanea_distinta_del_manifiesto_falla(corrida) -> None:
    edit_yaml(corrida / "manifest.yml", lambda m: m["protocol"].update(title="Otro título"))
    snapshot = fila(auditar(corrida), "protocol_snapshot")
    assert snapshot.status == "FAIL"
    assert "no coincide con `manifest.protocol`" in snapshot.detail


def test_protocol_snapshot_fichero_extra_advierte(corrida) -> None:
    (corrida / "00_protocol" / "notas.txt").write_text("apuntes\n", encoding="utf-8")
    snapshot = fila(auditar(corrida), "protocol_snapshot")
    assert snapshot.status == "WARN"
    assert "`notas.txt`" in snapshot.detail


def test_registration_lee_la_instantanea(corrida) -> None:
    # Solo la instantánea pierde el registro: el auditor la lee a ella.
    edit_yaml(corrida / "00_protocol" / "protocol.yml", lambda p: p.update(registration={}))
    assert fila(auditar(corrida), "registration").status == "WARN"
    editar_protocolo(corrida, lambda p: p.update(registration={"osf": "OSF-1"}))
    assert fila(auditar(corrida), "registration").status == "PASS"


# ── schemas de los artefactos de la Ola 1 ─────────────────────────────

ARTEFACTOS_OLA1 = (
    "01_search/records.json",
    "01_search/log.json",
    "02_dedup/records.json",
    "02_dedup/dedup.json",
    "03_screening/gold.json",
    "04_fulltext/retrieval.json",
    "04_fulltext/excluded.json",
    "run.json",
)


@pytest.mark.parametrize("rel", ARTEFACTOS_OLA1)
def test_schemas_artefacto_de_la_ola_1_invalido_falla(corrida, rel: str) -> None:
    (corrida / rel).write_text('{"no": "valida"}', encoding="utf-8")
    schemas = fila(auditar(corrida), "schemas")
    assert schemas.status == "FAIL"
    assert rel in schemas.detail


def test_schemas_linea_de_diario_invalida_falla_con_su_numero(corrida) -> None:
    path = corrida / "03_screening" / "journal.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[1] = lines[1].replace('"input_sha256"', '"input"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    schemas = fila(auditar(corrida), "schemas")
    assert schemas.status == "FAIL"
    assert "03_screening/journal.jsonl: línea 2: input_sha256: Field required" in schemas.detail


def test_schemas_llamada_sin_etapa_en_llm_calls_jsonl_falla(corrida) -> None:
    path = corrida / "llm_calls.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[0] = lines[0].replace('"stage":"screening_ta"', '"stage":"cribado"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    schemas = fila(auditar(corrida), "schemas")
    assert schemas.status == "FAIL"
    assert "llm_calls.jsonl: línea 1: stage" in schemas.detail


def test_schemas_retrieval_sin_motivo_de_fallo_falla(corrida) -> None:
    def _sin_motivo(rows: list[dict]) -> None:
        rows[0].update(available=False, reason=None)

    edit_json(corrida / "04_fulltext" / "retrieval.json", _sin_motivo)
    schemas = fila(auditar(corrida), "schemas")
    assert schemas.status == "FAIL"
    assert "04_fulltext/retrieval.json" in schemas.detail


# ── stage_artifacts y deliverable de la Ola 1 ─────────────────────────


@pytest.mark.parametrize(
    ("rel", "etapa"),
    [
        ("01_search/log.json", "busqueda"),
        ("02_dedup/dedup.json", "dedup"),
        ("03_screening/journal.jsonl", "screening_ta"),
        ("04_fulltext/excluded.json", "screening_ft"),
        ("05_extraction/journal_2.jsonl", "extraccion"),
        ("06_synthesis/verification.jsonl", "sintesis"),
    ],
)
def test_stage_artifacts_exige_los_artefactos_de_la_ola_1(corrida, rel: str, etapa: str) -> None:
    (corrida / rel).unlink()
    stage = fila(auditar(corrida), "stage_artifacts")
    assert stage.status == "FAIL"
    assert f"{etapa}: {rel}" in stage.detail


def test_deliverable_exige_la_lista_16b(corrida) -> None:
    (corrida / "deliverable" / "excluidos_texto_completo.md").unlink()
    deliverable = fila(auditar(corrida), "deliverable")
    assert deliverable.status == "FAIL"
    assert "excluidos_texto_completo.md (falta)" in deliverable.detail


# ── protocol_snapshot: más casos de D13 y de la comparación con run.json y el manifiesto ──────


def _sin_error_interno(report) -> list[str]:
    return [c.check_id for c in report.checks if "error interno" in c.detail]


def test_protocol_snapshot_run_json_que_no_valida_falla_y_remite_a_schemas(corrida) -> None:
    (corrida / "run.json").write_text('{"slug": 1}', encoding="utf-8")
    report = auditar(corrida)
    snapshot = fila(report, "protocol_snapshot")
    assert snapshot.status == "FAIL"
    assert "run.json ilegible o inválido" in snapshot.detail
    assert "(ver `schemas`)" in snapshot.detail
    assert fila(report, "schemas").status == "FAIL"  # la remisión es cierta


def test_protocol_snapshot_run_json_sin_la_huella_de_protocol_yml_falla(corrida) -> None:
    edit_json(corrida / "run.json", lambda info: info["protocol_sha256"].pop("protocol.yml"))
    snapshot = fila(auditar(corrida), "protocol_snapshot")
    assert snapshot.status == "FAIL"
    assert "run.json no registra la huella de `protocol.yml`" in snapshot.detail


def test_protocol_snapshot_no_depende_del_fin_de_linea(corrida) -> None:
    # Con `autocrlf` el mismo protocolo tiene otros bytes en otro clon: la huella es la del
    # texto con CRLF convertido a LF (spec §4.1), no la de los bytes.
    path = corrida / "00_protocol" / "protocol.yml"
    path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    assert b"\r\n" in path.read_bytes()
    assert fila(auditar(corrida), "protocol_snapshot").status == "PASS"


def test_protocol_snapshot_sin_la_carpeta_00_protocol_falla_con_los_ficheros_que_faltan(
    corrida,
) -> None:
    shutil.rmtree(corrida / "00_protocol")
    report = auditar(corrida)
    snapshot = fila(report, "protocol_snapshot")
    assert snapshot.status == "FAIL"
    assert "`00_protocol/effects.yml` ausente" in snapshot.detail
    assert "`00_protocol/protocol.yml` ausente" in snapshot.detail
    assert _sin_error_interno(report) == []
    assert not report.publishable


def test_protocol_snapshot_manifiesto_sin_protocol_falla(corrida) -> None:
    # El motor escribe `protocol` en todo manifiesto: que falte no deja la instantánea sin
    # contrastar.
    edit_yaml(corrida / "manifest.yml", lambda m: m.pop("protocol"))
    snapshot = fila(auditar(corrida), "protocol_snapshot")
    assert snapshot.status == "FAIL"
    assert "el manifiesto no trae `protocol`" in snapshot.detail


def test_protocol_snapshot_con_el_manifiesto_ilegible_solo_exige_que_valide(corrida) -> None:
    (corrida / "manifest.yml").write_text("{\n", encoding="utf-8")
    snapshot = fila(auditar(corrida), "protocol_snapshot")
    assert snapshot.status == "PASS"
    assert "sin manifiesto legible con el que compararla" in snapshot.detail


def test_protocol_snapshot_de_una_corrida_en_pausa_valida_sin_manifiesto(
    corrida_en_pausa_ft,
) -> None:
    # En una pausa el manifiesto aún no existe (spec §4.2), pero la instantánea sí: se verifica.
    assert not (corrida_en_pausa_ft / "manifest.yml").exists()
    report = auditar(corrida_en_pausa_ft)
    snapshot = fila(report, "protocol_snapshot")
    assert snapshot.status == "PASS"
    assert "sin manifiesto legible" in snapshot.detail
    assert fila(report, "stage_artifacts").status == "PASS"  # lo posterior no se exige aún


def test_protocol_snapshot_instantanea_que_no_valida_falla(corrida) -> None:
    # Hash coherente (run.json al día) pero protocolo inválido: `thresholds` fuera de rango.
    editar_protocolo(corrida, lambda p: p.update(thresholds={"recall_target": 1.5}))
    huellas = protocol_fingerprint(corrida / "00_protocol")
    edit_json(corrida / "run.json", lambda info: info["protocol_sha256"].update(huellas))
    snapshot = fila(auditar(corrida), "protocol_snapshot")
    assert snapshot.status == "FAIL"
    assert "`00_protocol/protocol.yml` no valida" in snapshot.detail


def test_protocol_sale_de_la_instantanea_aunque_el_manifiesto_diga_otra_cosa(corrida) -> None:
    # Solo el manifiesto cambia: los checks siguen midiendo con el protocolo congelado y
    # `protocol_snapshot` marca la discrepancia.
    edit_yaml(
        corrida / "manifest.yml",
        lambda m: m["protocol"].update(thresholds={"recall_target": 0.5}),
    )
    report = auditar(corrida)
    assert "≥ 0.95" in fila(report, "thresholds").detail  # el de la instantánea
    assert fila(report, "protocol_snapshot").status == "FAIL"
    ctx = AuditContext(load_run(corrida))
    assert ctx.protocol is not None and ctx.protocol.thresholds["recall_target"] == 0.95
    assert ctx.protocol_raw["thresholds"]["recall_target"] == 0.95


def test_protocol_de_una_corrida_anterior_a_la_ola_1_sale_del_manifiesto(tmp_path) -> None:
    ctx = AuditContext(load_run(write_legacy_v07(tmp_path)))
    assert ctx.protocol is not None and ctx.protocol.slug == "legado-v07"
    assert ctx.protocol_raw is not None and ctx.protocol_raw["slug"] == "legado-v07"
    assert ctx.llm_calls == ctx.manifest_llm_calls and len(ctx.llm_calls) == 12


def test_snapshot_protocol_toma_el_slug_de_run_json_si_el_protocolo_no_lo_declara(corrida) -> None:
    # El protocolo del demo no declara `slug`: al reanudar, `load_protocol` usa el de run.json y
    # el nombre de la carpeta `00_protocol/` no es el slug (spec §2, hallazgo 4).
    texto = (corrida / "00_protocol" / "protocol.yml").read_text(encoding="utf-8")
    assert "slug:" not in texto
    snapshot = AuditContext(load_run(corrida)).snapshot_protocol
    assert snapshot.ok and snapshot.value.slug == "demo-mini-review"


def test_registration_y_search_window_sin_instantanea_legible_leen_el_manifiesto(corrida) -> None:
    # Con `protocol.yml` roto en la instantánea, el protocolo en crudo es el del manifiesto.
    (corrida / "00_protocol" / "protocol.yml").write_text("a: [sin cerrar\n", encoding="utf-8")
    report = auditar(corrida)
    assert fila(report, "registration").status == "PASS"
    assert fila(report, "protocol_snapshot").status == "FAIL"


# ── Claves de fusión en la instantánea: el motivo no dice «del motor» ─────────────────────────


def _protocolo_con_fusion(corrida) -> None:
    path = corrida / "00_protocol" / "protocol.yml"
    texto = path.read_text(encoding="utf-8")
    path.write_text(texto + "extra: {<<: {k: 1}}\n", encoding="utf-8")


def test_instantanea_con_claves_de_fusion_falla_con_un_motivo_neutro(corrida) -> None:
    _protocolo_con_fusion(corrida)
    snapshot = fila(auditar(corrida), "protocol_snapshot")
    assert snapshot.status == "FAIL"
    assert "claves de fusión YAML (<<) no admitidas por el auditor" in snapshot.detail
    assert "riesgo de expansión exponencial" in snapshot.detail
    assert "del motor" not in snapshot.detail


def test_artefacto_del_motor_con_claves_de_fusion_sigue_diciendo_del_motor(corrida) -> None:
    # Solo `00_protocol/` es del usuario: un manifiesto con `<<` lo escribió otro.
    manifiesto = corrida / "manifest.yml"
    manifiesto.write_text(
        manifiesto.read_text(encoding="utf-8") + "extra: {<<: {k: 1}}\n", encoding="utf-8"
    )
    assert "artefactos del motor" in fila(auditar(corrida), "manifest").detail


def test_bomba_de_fusion_en_la_instantanea_no_cuelga_el_auditor(corrida) -> None:
    # Nueve alias por nivel, diez niveles: la guarda la rechaza sin cargarla (en un subproceso,
    # por si colgara o muriera).
    bomba = "a0: &a0 {k: 1}\n" + "".join(
        f"a{i}: &a{i} {{<<: [{', '.join([f'*a{i - 1}'] * 9)}]}}\n" for i in range(1, 10)
    )
    path = corrida / "00_protocol" / "protocol.yml"
    path.write_text(bomba + path.read_text(encoding="utf-8"), encoding="utf-8")
    filas = auditar_en_subproceso(corrida, timeout=60)
    estado, detalle = filas["protocol_snapshot"]
    assert estado == "FAIL"
    assert "claves de fusión YAML (<<) no admitidas por el auditor" in detalle
    assert len(detalle) < 1_500
    assert [i for i, (_, d) in filas.items() if "error interno" in d] == []
    assert len(filas) == len(CHECKS)


def test_bomba_de_alias_en_el_protocolo_de_la_instantanea_no_cuelga_el_auditor(corrida) -> None:
    # Un alias normal (`*a9`) comparte nodos y carga al instante; recorrerlo (`repr`, validar)
    # costaría 9**10 hojas. La instantánea es entrada no confiable como el manifiesto.
    path = corrida / "00_protocol" / "protocol.yml"
    cola = "search_window: {from: '2015-01-01', to: '2026-06-26', executed: *a9}\ntitle: *a9\n"
    path.write_text(bomba_de_alias() + path.read_text(encoding="utf-8") + cola, encoding="utf-8")
    filas = auditar_en_subproceso(corrida, timeout=60)
    assert filas["protocol_snapshot"][0] == "FAIL"
    assert filas["search_window"][0] == "WARN"
    for check_id in ("protocol_snapshot", "search_window", "registration", "thresholds"):
        assert len(filas[check_id][1]) < 1_500, check_id
    assert [i for i, (_, d) in filas.items() if "error interno" in d] == []
    assert len(filas) == len(CHECKS)


# ── Entrada hostil en protocol_snapshot: ningún valor de run.json o de 00_protocol/ la rompe ──


def test_protocol_snapshot_run_json_con_miles_de_huellas_enormes_se_acota(corrida) -> None:
    def _hostil(info: dict) -> None:
        for i in range(20_000):
            info["protocol_sha256"][f"x{i}"] = "h"
        for i in range(20):
            info["protocol_sha256"][f"{'y' * 50_000}-{i}"] = "h" * 50_000
        info["protocol_sha256"]["inclusion_exclusion.yml"] = "h" * 50_000

    edit_json(corrida / "run.json", _hostil)
    report = auditar(corrida)
    snapshot = fila(report, "protocol_snapshot")
    assert snapshot.status == "FAIL"
    assert "`00_protocol/inclusion_exclusion.yml`: hash distinto del de run.json" in snapshot.detail
    assert "(+20015 ficheros más)" in snapshot.detail  # lo que no se lista se cuenta
    assert len(snapshot.detail) < 1_500
    assert _sin_error_interno(report) == []
    assert len(report.checks) == len(CHECKS)


def test_protocol_snapshot_protocolo_de_50000_caracteres_se_acota(corrida) -> None:
    editar_protocolo(corrida, lambda p: p.update(title="t" * 50_000))
    edit_yaml(corrida / "manifest.yml", lambda m: m["protocol"].update(title="u" * 50_000))
    report = auditar(corrida)
    snapshot = fila(report, "protocol_snapshot")
    assert snapshot.status == "FAIL"
    assert len(snapshot.detail) < 1_500
    assert _sin_error_interno(report) == []


@pytest.mark.parametrize(
    "preparar",
    [
        pytest.param(
            lambda c: (c / "00_protocol" / "effects.yml").write_bytes(b"\xff\xfe\x00 no es utf-8"),
            id="fichero-que-no-es-utf-8",
        ),
        pytest.param(
            lambda c: (c / "00_protocol" / "search_strings" / "trampa.txt").mkdir(),
            id="directorio-con-nombre-de-cadena-de-busqueda",
        ),
    ],
)
def test_protocol_snapshot_instantanea_ilegible_falla_sin_reventar(corrida, preparar) -> None:
    preparar(corrida)
    report = auditar(corrida)
    snapshot = fila(report, "protocol_snapshot")
    assert snapshot.status == "FAIL"
    assert "no se pudo calcular la huella de 00_protocol/" in snapshot.detail
    assert _sin_error_interno(report) == []
    assert len(report.checks) == len(CHECKS)


def test_protocol_snapshot_miles_de_ficheros_extra_se_acotan(corrida) -> None:
    extra = corrida / "00_protocol" / "extra"
    extra.mkdir()
    for i in range(1_500):
        (extra / f"nota-{i:04d}.txt").write_text("x\n", encoding="utf-8")
    snapshot = fila(auditar(corrida), "protocol_snapshot")
    assert snapshot.status == "WARN"
    assert "(+1495 más)" in snapshot.detail
    assert len(snapshot.detail) < 1_500


# ── schemas de los .jsonl y de los artefactos nuevos con valores hostiles ─────────────────────


def _lineas(path) -> list[str]:
    return path.read_text(encoding="utf-8").split("\n")[:-1]


def test_schemas_diario_con_miles_de_lineas_rotas_se_acota(corrida) -> None:
    path = corrida / "03_screening" / "journal.jsonl"
    rotas = ['{"x": 1}'] * 3_000 + ["{no es json"] * 3_000
    path.write_text("\n".join([*_lineas(path), *rotas]) + "\n", encoding="utf-8")
    report = auditar(corrida)
    schemas = fila(report, "schemas")
    assert schemas.status == "FAIL"
    assert "03_screening/journal.jsonl: " in schemas.detail
    assert len(schemas.detail) < 1_500
    assert "\\" + "u000a" not in schemas.detail  # el salto de línea no se escapa
    assert _sin_error_interno(report) == []


def test_schemas_jsonl_con_una_linea_de_50000_caracteres_se_acota(corrida) -> None:
    path = corrida / "llm_calls.jsonl"
    lineas = _lineas(path)
    hostil = json.dumps({"stage": "x" * 50_000, "provider": "p" * 50_000})
    path.write_text("\n".join([hostil, *lineas[1:]]) + "\n", encoding="utf-8")
    report = auditar(corrida)
    schemas = fila(report, "schemas")
    assert schemas.status == "FAIL"
    assert "llm_calls.jsonl: línea 1: " in schemas.detail
    assert len(schemas.detail) < 1_500
    assert _sin_error_interno(report) == []
    assert len(report.checks) == len(CHECKS)


def test_schemas_jsonl_con_lineas_que_no_son_mapas_no_revienta_a_los_demas_checks(corrida) -> None:
    path = corrida / "llm_calls.jsonl"
    lineas = _lineas(path)
    path.write_text("\n".join(["[1, 2, 3]", '"texto"', "7", *lineas[3:]]) + "\n", encoding="utf-8")
    report = auditar(corrida)
    assert fila(report, "schemas").status == "FAIL"
    assert _sin_error_interno(report) == []
    assert len(report.checks) == len(CHECKS)


def test_schemas_jsonl_ilegible_como_texto_falla_sin_reventar(corrida) -> None:
    (corrida / "03_screening" / "journal.jsonl").write_bytes(b"\xff\xfe no es utf-8\n")
    report = auditar(corrida)
    schemas = fila(report, "schemas")
    assert schemas.status == "FAIL"
    assert "03_screening/journal.jsonl: no es texto UTF-8" in schemas.detail
    assert _sin_error_interno(report) == []


@pytest.mark.parametrize("rel", [r for r in ARTEFACTOS_OLA1 if r != "03_screening/gold.json"])
def test_schemas_artefacto_de_la_ola_1_con_claves_de_50000_caracteres_se_acota(
    corrida, rel: str
) -> None:
    (corrida / rel).write_text(json.dumps({"k" * 50_000: "v" * 50_000}), encoding="utf-8")
    report = auditar(corrida)
    schemas = fila(report, "schemas")
    assert schemas.status == "FAIL"
    assert rel in schemas.detail
    assert len(schemas.detail) < 1_500
    assert _sin_error_interno(report) == []
    assert len(report.checks) == len(CHECKS)


def test_schemas_gold_json_con_clave_de_50000_caracteres_se_acota(corrida) -> None:
    # La clave del gold es un `record_id`: va en el `loc` del error de pydantic.
    (corrida / "03_screening" / "gold.json").write_text(
        json.dumps({"k" * 50_000: "no es un booleano"}), encoding="utf-8"
    )
    report = auditar(corrida)
    schemas = fila(report, "schemas")
    assert schemas.status == "FAIL"
    assert "03_screening/gold.json" in schemas.detail
    assert len(schemas.detail) < 1_500
    assert _sin_error_interno(report) == []


@pytest.mark.parametrize(
    ("bloque", "valor"),
    [
        pytest.param("run", {"status": "x" * 50_000}, id="run"),
        pytest.param("autonomy_effective", {"k" * 50_000: 5}, id="autonomy_effective"),
        pytest.param("final_gate", {"forced_human": "sí", "reason": 7}, id="final_gate"),
        pytest.param("final_gate", {"forced_human": 1}, id="final_gate-entero-no-es-booleano"),
    ],
)
def test_schemas_bloque_nuevo_del_manifiesto_invalido_falla_acotado(
    corrida, bloque: str, valor: dict
) -> None:
    edit_yaml(corrida / "manifest.yml", lambda m: m.update({bloque: valor}))
    report = auditar(corrida)
    schemas = fila(report, "schemas")
    assert schemas.status == "FAIL"
    assert f"manifest.yml#{bloque}" in schemas.detail
    assert len(schemas.detail) < 1_500
    assert _sin_error_interno(report) == []


def test_schemas_valida_los_nueve_jsonl_de_una_corrida_real(corrida) -> None:
    # Los ocho diarios y `llm_calls.jsonl` existen en la corrida de los tests y validan: la
    # cuenta del PASS sube por cada uno.
    ctx = AuditContext(load_run(corrida))
    for rel in JSONL_ADAPTERS:
        cargado = ctx.art.jsonl_models(rel)
        assert cargado.ok and cargado.value, rel
        assert all(isinstance(numero, int) for numero, _ in cargado.value)
    schemas = fila(auditar(corrida), "schemas")
    assert schemas.status == "PASS"
    assert schemas.detail.endswith(" artefactos validan su modelo.")


# ── decision.yml: HumanDecision con run.json, LegacyDecision sin él ───────────────────────────


def test_schemas_decision_legada_en_una_corrida_de_la_ola_1_falla(corrida) -> None:
    # Con `run.json` la decisión debe atarse a su solicitud (D4): el formato v0.7 no vale.
    (corrida / "screening_ta" / "decision.yml").write_text(
        "approved: true\nactor: human:revisora\n", encoding="utf-8"
    )
    schemas = fila(auditar(corrida), "schemas")
    assert schemas.status == "FAIL"
    assert "screening_ta/decision.yml: request_sha256: Field required" in schemas.detail


@pytest.mark.parametrize(
    ("contenido", "motivo"),
    [
        pytest.param("actor: human:revisora\n", "approved: Field required", id="sin-approved"),
        pytest.param(
            "approved: 'true'\n", "approved: Input should be a valid boolean", id="cadena"
        ),
        pytest.param(
            "approved: true\nactor: [a]\n", "actor: Input should be a valid string", id="actor"
        ),
    ],
)
def test_schemas_decision_legada_invalida_falla_con_su_modelo(
    tmp_path, contenido: str, motivo: str
) -> None:
    run = write_legacy_v07(tmp_path)
    (run / "screening_ta" / "decision.yml").write_text(contenido, encoding="utf-8")
    schemas = fila(auditar(run), "schemas")
    assert schemas.status == "FAIL"
    assert f"screening_ta/decision.yml: {motivo}" in schemas.detail


def test_schemas_decision_legada_con_campos_extra_valida(tmp_path) -> None:
    run = write_legacy_v07(tmp_path)
    (run / "rob" / "decision.yml").write_text(
        "approved: true\nactor: human:revisora\nnota: algo que v0.7 permitía\n", encoding="utf-8"
    )
    assert fila(auditar(run), "schemas").status == "PASS"


# ── stage_artifacts: qué diarios exige cada etapa, y cuáles no ────────────────────────────────


@pytest.mark.parametrize(
    ("rel", "etapa"),
    [
        ("00_protocol/protocol.yml", "protocolo"),
        ("01_search/records.json", "busqueda"),
        ("02_dedup/records.json", "dedup"),
        ("llm_calls.jsonl", "screening_ta"),
        ("04_fulltext/retrieval.json", "screening_ft"),
        ("04_fulltext/retrieval.jsonl", "screening_ft"),
        ("04_fulltext/journal.jsonl", "screening_ft"),
        ("05_extraction/journal.jsonl", "extraccion"),
        ("07_rob/journal.jsonl", "rob"),
        ("06_synthesis/journal.jsonl", "sintesis"),
    ],
)
def test_stage_artifacts_exige_tambien_el_resto_de_artefactos_de_la_ola_1(
    corrida, rel: str, etapa: str
) -> None:
    (corrida / rel).unlink()
    stage = fila(auditar(corrida), "stage_artifacts")
    assert stage.status == "FAIL"
    assert f"{etapa}: {rel}" in stage.detail


def test_stage_artifacts_sin_run_json_no_exige_los_artefactos_de_la_ola_1(tmp_path) -> None:
    # Una corrida anterior a la Ola 1 no los tiene: ya falla `protocol_snapshot` (D13) y el
    # resto se audita como diagnóstico, sin ruido de ficheros que su motor no escribía.
    stage = fila(auditar(write_legacy_v07(tmp_path)), "stage_artifacts")
    assert stage.status == "PASS"


def test_stage_artifacts_sin_diario_de_recuperacion_si_todos_los_fallos_fueron_transitorios(
    corrida,
) -> None:
    # El motor no escribe en el diario los fallos de red (se reintentan al reanudar): una corrida
    # cuyas recuperaciones fallaron todas así no tiene `retrieval.jsonl` y no es manipulación.
    def _todos_transitorios(rows: list[dict]) -> None:
        for row in rows:
            row.update(available=False, reason="error_http", n_chars=0)

    edit_json(corrida / "04_fulltext" / "retrieval.json", _todos_transitorios)
    (corrida / "04_fulltext" / "retrieval.jsonl").unlink()
    assert fila(auditar(corrida), "stage_artifacts").status == "PASS"


def test_stage_artifacts_exige_el_diario_de_recuperacion_si_retrieval_json_no_se_lee(
    corrida,
) -> None:
    # Fail-closed: sin saber qué resultados hubo, el diario se exige (y `schemas` marca el fichero).
    (corrida / "04_fulltext" / "retrieval.json").write_text("{no es json", encoding="utf-8")
    (corrida / "04_fulltext" / "retrieval.jsonl").unlink()
    stage = fila(auditar(corrida), "stage_artifacts")
    assert stage.status == "FAIL"
    assert "04_fulltext/retrieval.jsonl" in stage.detail


def test_stage_artifacts_no_exige_el_diario_de_ft_sin_ningun_registro_cribado(corrida) -> None:
    def _sin_votos(decisions: list[dict]) -> None:
        for decision in decisions:
            decision.update(votes=[], ensemble_label=None, fulltext_status="not_retrieved")

    edit_json(corrida / "04_fulltext" / "decisions.json", _sin_votos)
    (corrida / "04_fulltext" / "journal.jsonl").unlink()
    assert fila(auditar(corrida), "stage_artifacts").status == "PASS"


def test_stage_artifacts_no_exige_lo_de_etapas_que_la_corrida_no_alcanzo(
    corrida_en_pausa_ft,
) -> None:
    # Pausada en `screening_ft`: ni el diario de FT ni la lista de excluidos existen todavía.
    assert not (corrida_en_pausa_ft / "04_fulltext" / "excluded.json").exists()
    stage = fila(auditar(corrida_en_pausa_ft), "stage_artifacts")
    assert stage.status == "PASS"
    assert "screening_ft" not in stage.detail


def test_stage_artifacts_cuantas_etapas_dice_el_pass(corrida) -> None:
    stage = fila(auditar(corrida), "stage_artifacts")
    assert stage.status == "PASS"
    assert "de 9 etapas alcanzadas presentes (protocolo, busqueda, dedup, screening_ta" in (
        stage.detail
    )


# ── Las llamadas IA: la fuente es llm_calls.jsonl y el manifiesto es su copia ─────────────────


def test_llm_calls_de_una_corrida_de_la_ola_1_salen_de_llm_calls_jsonl(corrida) -> None:
    path = corrida / "llm_calls.jsonl"
    lineas = _lineas(path)
    path.write_text("\n".join(lineas[:-1]) + "\n", encoding="utf-8")
    ctx = AuditContext(load_run(corrida))
    assert len(ctx.llm_calls) == len(lineas) - 1
    assert len(ctx.manifest_llm_calls) == len(lineas)  # la copia del manifiesto no se tocó
    assert fila(auditar(corrida), "prompts").detail.startswith(
        f"{len(lineas) - 1}/{len(lineas) - 1}"
    )


def test_arithmetic_copia_de_llm_calls_distinta_del_original_falla(corrida) -> None:
    def _quitar_la_ultima(manifest: dict) -> None:
        manifest["llm_calls"].pop()

    edit_yaml(corrida / "manifest.yml", _quitar_la_ultima)
    report = auditar(corrida)
    arithmetic = fila(report, "arithmetic")
    assert arithmetic.status == "FAIL"
    assert "§4.3 · manifest.llm_calls == líneas de llm_calls.jsonl" in arithmetic.detail
    assert not report.publishable


def test_arithmetic_llm_calls_jsonl_editado_sin_el_manifiesto_falla(corrida) -> None:
    path = corrida / "llm_calls.jsonl"
    path.write_text("\n".join(_lineas(path)[:-1]) + "\n", encoding="utf-8")
    arithmetic = fila(auditar(corrida), "arithmetic")
    assert arithmetic.status == "FAIL"
    assert "manifest.llm_calls == líneas de llm_calls.jsonl" in arithmetic.detail


def test_manifest_comprueba_las_llamadas_que_el_manifiesto_dice_tener(corrida) -> None:
    # `manifest` audita al manifiesto; que su copia coincida con el original es de `arithmetic`.
    edit_yaml(corrida / "manifest.yml", lambda m: m.update(llm_calls=[], models_used=[]))
    manifest = fila(auditar(corrida), "manifest")
    assert manifest.status == "WARN"
    assert "sin llamadas IA" in manifest.detail


def test_llm_calls_jsonl_con_un_proveedor_de_50000_caracteres_se_acota(corrida) -> None:
    def _hostil(calls: list[dict]) -> None:
        calls[0]["provider"] = "p" * 50_000

    editar_llamadas(corrida, _hostil)
    report = auditar(corrida)
    assert _sin_error_interno(report) == []
    for check in report.checks:
        assert len(check.detail) < 2_000, check.check_id
    assert len(report.checks) == len(CHECKS)


# ── La lista 16b del entregable ───────────────────────────────────────────────────────────────


def test_deliverable_sin_run_json_no_exige_la_lista_16b(tmp_path) -> None:
    deliverable = fila(auditar(write_legacy_v07(tmp_path)), "deliverable")
    assert deliverable.status == "PASS"
    assert "excluidos_texto_completo" not in deliverable.detail


def test_deliverable_lista_16b_vacia_o_binaria_falla_sin_reventar(corrida) -> None:
    lista = corrida / "deliverable" / "excluidos_texto_completo.md"
    lista.write_text("  \n", encoding="utf-8")
    assert "excluidos_texto_completo.md (vacío)" in fila(auditar(corrida), "deliverable").detail
    lista.write_bytes(b"\xff\xfe\x00 no es utf-8")
    deliverable = fila(auditar(corrida), "deliverable")
    assert deliverable.status == "FAIL"
    assert "excluidos_texto_completo.md" in deliverable.detail
    assert "error interno" not in deliverable.detail


# ── jsonl_models: el contrato del cargador ────────────────────────────────────────────────────


def test_jsonl_models_separa_las_lineas_validas_de_las_invalidas(corrida) -> None:
    path = corrida / "03_screening" / "journal.jsonl"
    lineas = _lineas(path)
    path.write_text(
        "\n".join([lineas[0], "{no es json", '{"x": 1}', lineas[1]]) + "\n", encoding="utf-8"
    )
    cargado = AuditContext(load_run(corrida)).art.jsonl_models("03_screening/journal.jsonl")
    assert not cargado.ok
    assert [n for n, _ in cargado.value] == [1, 4]  # las válidas, con su número de línea
    assert cargado.error.startswith("línea 2: JSON inválido")
    assert "línea 3: " in cargado.error and "\n" not in cargado.error


def test_jsonl_models_de_un_fichero_ausente_no_esta_presente(corrida) -> None:
    (corrida / "07_rob" / "journal.jsonl").unlink()
    cargado = AuditContext(load_run(corrida)).art.jsonl_models("07_rob/journal.jsonl")
    assert not cargado.present and cargado.ok is False and cargado.error is None


def test_schemas_decision_legada_con_valores_de_50000_caracteres_se_acota(tmp_path) -> None:
    run = write_legacy_v07(tmp_path)
    (run / "screening_ta" / "decision.yml").write_text(
        f"approved: {'x' * 50_000}\nactor: {'a' * 50_000}\nreason: {'r' * 50_000}\n",
        encoding="utf-8",
    )
    report = auditar(run)
    schemas = fila(report, "schemas")
    assert schemas.status == "FAIL"
    assert "screening_ta/decision.yml: approved: Input should be a valid boolean" in schemas.detail
    assert len(schemas.detail) < 1_500
    assert _sin_error_interno(report) == []


def test_stage_artifacts_con_una_recuperacion_de_detalle_enorme_no_la_vuelca(corrida) -> None:
    edit_json(
        corrida / "04_fulltext" / "retrieval.json",
        lambda rows: rows[0].update(detail="d" * 50_000, source_url="u" * 50_000),
    )
    report = auditar(corrida)
    stage = fila(report, "stage_artifacts")
    assert stage.status == "PASS"
    assert len(stage.detail) < 500
    assert fila(report, "schemas").status == "PASS"  # son cadenas válidas: lo hostil es su tamaño
    assert _sin_error_interno(report) == []
