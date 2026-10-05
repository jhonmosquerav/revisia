"""Plausibilidad temporal: ``timing`` y ``response_overlap`` (spec 2026-10-04 §9.3).

Las heurísticas solo dan WARN; lo imposible (marcas fuera de la corrida, sin
zona, ledger que retrocede, determinismo declarado por un proveedor real) da
FAIL. Las corridas ``fake`` deterministas están exentas de las heurísticas.

El manifiesto, el ledger y las llamadas son entrada no confiable: ninguna marca,
proveedor ni modelo hostil (cadenas enormes, tipos raros, bombas de alias,
fechas en el límite del calendario) cuelga ni rompe el auditor, y ningún
detalle los reproduce sin acotar (revisiones de la Tarea 4).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from audit_fixtures import (
    auditar,
    auditar_en_subproceso,
    bomba_de_alias,
    comprimir_llamadas,
    edit_ledger,
    edit_yaml,
    editar_llamadas,
    fila,
    primera_llamada,
    reetiquetar_llamadas,
)

from revisia.audit import render_audit_md
from revisia.audit.checks_timing import parse_utc
from revisia.schemas.artifacts import RunInfo


def test_timing_corrida_real_pasa(corrida) -> None:
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "PASS"
    assert "exentas de las heurísticas" in timing.detail


def test_timing_llamadas_en_1_3_ms_solo_advierte(corrida) -> None:
    # Síntoma C3: 24 llamadas no fake en 1,3 ms. Es una heurística: WARN, no FAIL.
    comprimir_llamadas(corrida)
    report = auditar(corrida)
    timing = fila(report, "timing")
    assert timing.status == "WARN"
    assert "24 llamadas no fake con una mediana de 0.057 ms" in timing.detail
    assert "API por lotes" in timing.detail
    assert report.publishable


def test_timing_fake_determinista_exento_aunque_sea_instantaneo(corrida) -> None:
    reetiquetar_llamadas(
        corrida,
        provider="fake",
        deterministic=True,
        inicio=primera_llamada(corrida),
        paso=timedelta(microseconds=10),
    )
    assert fila(auditar(corrida), "timing").status == "PASS"


def test_timing_determinista_no_fake_falla(corrida) -> None:
    reetiquetar_llamadas(corrida, provider="gemini", deterministic=True)
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "FAIL"
    assert "`deterministic: true` con proveedor `gemini`" in timing.detail


def _desplazar_ledger(run, delta: timedelta) -> None:
    def _editar(entries: list[dict]) -> None:
        for entry in entries:
            marca = datetime.fromisoformat(entry["timestamp_utc"]) + delta
            entry["timestamp_utc"] = marca.isoformat()

    edit_ledger(run, _editar)


def test_timing_ledger_anterior_al_inicio_falla(corrida) -> None:
    # Síntoma C3: ledger fechado una semana antes de la corrida.
    _desplazar_ledger(corrida, -timedelta(days=7))
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "FAIL"
    assert "ledger línea 1 anterior al inicio de la corrida" in timing.detail


def test_timing_llamada_posterior_al_manifiesto_falla(corrida) -> None:
    def _tarde(calls: list[dict]) -> None:
        calls[-1]["timestamp_utc"] = "2099-01-01T00:00:00.123456+00:00"

    editar_llamadas(corrida, _tarde)
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "FAIL"
    assert "llm_calls[23] posterior al manifiesto" in timing.detail


def test_timing_marca_sin_zona_falla(corrida) -> None:
    edit_ledger(corrida, lambda e: e[0].update(timestamp_utc="2026-10-04T12:00:00.5"))
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "FAIL"
    assert "ledger línea 1: sin zona horaria" in timing.detail


def test_timing_ledger_que_retrocede_falla(corrida) -> None:
    def _adelantar_la_segunda(entries: list[dict]) -> None:
        marca = datetime.fromisoformat(entries[1]["timestamp_utc"]) + timedelta(seconds=30)
        entries[1]["timestamp_utc"] = marca.isoformat()

    edit_ledger(corrida, _adelantar_la_segunda)
    final = primera_llamada(corrida) + timedelta(minutes=5)
    edit_yaml(corrida / "manifest.yml", lambda m: m.update(created_utc=final.isoformat()))
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "FAIL"
    assert "ledger línea 3: retrocede" in timing.detail


def test_timing_pausa_de_dias_sin_aviso(corrida) -> None:
    # Una pausa humana de días no mueve la mediana: llamadas reales cada 400 ms,
    # con la mitad tres días después. Sin WARN ni FAIL.
    inicio = primera_llamada(corrida)

    def _pausa(calls: list[dict]) -> None:
        for i, call in enumerate(calls):
            call.update(provider="gemini", deterministic=False)
            pausa = timedelta(days=3) if i >= 12 else timedelta(0)
            call["timestamp_utc"] = (inicio + i * timedelta(milliseconds=400) + pausa).isoformat()

    editar_llamadas(corrida, _pausa)
    final = inicio + timedelta(days=3, hours=1)
    edit_yaml(corrida / "manifest.yml", lambda m: m.update(created_utc=final.isoformat()))
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "PASS", timing.detail
    assert "mediana entre llamadas no fake 400 ms" in timing.detail


def test_timing_horas_redondas_en_el_ledger_advierten(corrida) -> None:
    def _redondear(entries: list[dict]) -> None:
        for entry in entries:
            marca = datetime.fromisoformat(entry["timestamp_utc"]).replace(microsecond=0)
            entry["timestamp_utc"] = marca.isoformat()

    edit_ledger(corrida, _redondear)
    n = len((corrida / "decisions_ledger.jsonl").read_text(encoding="utf-8").splitlines())
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "WARN"
    assert f"{n}/{n} marcas del ledger sin fracción de segundo" in timing.detail


def test_timing_limite_inferior_no_verificable_advierte(corrida) -> None:
    # Sin run.json, el inicio sale de `manifest.timestamp`; "TEST" no se puede leer.
    (corrida / "run.json").unlink(missing_ok=True)
    edit_yaml(corrida / "manifest.yml", lambda m: m.update(timestamp="TEST"))
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "WARN"
    assert "límite inferior no verificable (timestamp `TEST`" in timing.detail


def test_timing_timestamp_con_forma_de_corrida_pero_fecha_imposible_advierte(corrida) -> None:
    # `20261304-250000` cumple `%Y%m%d-%H%M%S` por forma, pero no es una fecha: `strptime`
    # lanzaría y el auditor lo convertiría en «error interno» en vez de decir que no verifica.
    (corrida / "run.json").unlink(missing_ok=True)
    edit_yaml(corrida / "manifest.yml", lambda m: m.update(timestamp="20261304-250000"))
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "WARN"
    assert "límite inferior no verificable (timestamp `20261304-250000`" in timing.detail


def test_timing_sin_created_utc_el_limite_superior_no_es_verificable(corrida) -> None:
    # Un manifiesto editado a mano sin `created_utc` no puede dar PASS: borrar la clave no
    # relaja la comprobación del límite superior (falla abierto si solo se mira «si está»).
    def _tarde(calls: list[dict]) -> None:
        calls[-1]["timestamp_utc"] = "2099-01-01T00:00:00.123456+00:00"

    editar_llamadas(corrida, _tarde)
    edit_yaml(corrida / "manifest.yml", lambda m: m.pop("created_utc"))
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "WARN"
    assert "límite superior no verificable (manifest.created_utc ausente)" in timing.detail
    assert "dentro de [inicio, manifiesto]" not in timing.detail


def test_timing_con_manifiesto_ilegible_el_limite_superior_no_es_verificable(corrida) -> None:
    _escribir_run_json(corrida, primera_llamada(corrida) - timedelta(seconds=1))
    (corrida / "manifest.yml").write_text("{\n", encoding="utf-8")
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "WARN"
    assert "límite superior no verificable (manifiesto ilegible)" in timing.detail


def test_timing_en_una_corrida_en_pausa_dice_que_el_manifiesto_aun_no_existe(
    detener_corrida,
) -> None:
    # Una corrida real en pausa en `extraccion` todavía no escribió el manifiesto (spec §4.2):
    # llamarlo «ilegible» culpaba a un fichero que no existe.
    corrida = detener_corrida(aprobados=("screening_ta", "screening_ft"))
    assert not (corrida / "manifest.yml").exists()
    report = auditar(corrida)
    assert report.state is not None and report.state.status == "paused"
    timing = fila(report, "timing")
    assert timing.status == "WARN"
    assert (
        "límite superior no verificable: manifiesto ausente (corrida sin decisión final)"
        in timing.detail
    )
    assert "ilegible" not in timing.detail
    assert fila(report, "final_gate").status == "FAIL"


def test_timing_con_el_manifiesto_borrado_de_una_corrida_terminada_no_habla_de_pausa(
    corrida,
) -> None:
    # Ausente, pero la corrida llegó al gate final: el manifiesto debería existir, y «sin
    # decisión final» sería falso. La ausencia la marca `manifest`.
    (corrida / "manifest.yml").unlink()
    report = auditar(corrida)
    timing = fila(report, "timing")
    assert timing.status == "WARN"
    assert "límite superior no verificable: manifiesto ausente" in timing.detail
    assert "sin decisión final" not in timing.detail
    assert "ilegible" not in timing.detail
    assert fila(report, "manifest").status == "FAIL"


def test_timing_con_todo_verificado_nombra_ambos_limites(corrida) -> None:
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "PASS"
    assert "marcas dentro de [inicio, manifiesto] ±2 s" in timing.detail


def test_timing_llamadas_fake_mezcladas_con_reales_no_se_declaran_todas_exentas(corrida) -> None:
    # 23 fake deterministas y 1 real: no hay intervalos que medir entre las no fake, pero el
    # detalle no puede afirmar que *todas* las llamadas están exentas.
    def _una_real(calls: list[dict]) -> None:
        calls[-1].update(provider="gemini", deterministic=False)

    editar_llamadas(corrida, _una_real)
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "PASS", timing.detail
    assert "23 de 24 llamadas fake deterministas exentas" in timing.detail
    assert "1 no fake: sin intervalos que medir" in timing.detail
    assert "exentas de las heurísticas" not in timing.detail


def test_timing_con_dos_reales_y_el_resto_fake_cuenta_las_exentas(corrida) -> None:
    def _dos_reales(calls: list[dict]) -> None:
        for call in calls[-2:]:
            call.update(provider="gemini", deterministic=False)

    editar_llamadas(corrida, _dos_reales)
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "PASS", timing.detail
    assert "mediana entre llamadas no fake" in timing.detail
    assert "22 de 24 llamadas fake deterministas exentas" in timing.detail


def test_timing_con_una_sola_llamada_real_no_dice_que_es_fake(corrida) -> None:
    def _una(calls: list[dict]) -> list[dict]:
        calls[0].update(provider="gemini", deterministic=False)
        return calls[:1]

    editar_llamadas(corrida, _una)
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "PASS", timing.detail
    assert "fake deterministas" not in timing.detail
    assert "1 no fake: sin intervalos que medir" in timing.detail


def test_timing_sustituto_suelto_en_el_ledger_no_rompe_el_informe(corrida) -> None:
    # Un `"\ud800"` JSON deja un sustituto suelto en la cadena: no codifica a UTF-8 y
    # `revisia audit` escribe `audit.md` con `encoding="utf-8"`. El detalle debe ser siempre
    # codificable.
    ruta = corrida / "decisions_ledger.jsonl"
    ultima = json.loads(ruta.read_text(encoding="utf-8").splitlines()[-1])
    ultima["timestamp_utc"] = "\ud800"
    with ruta.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(ultima) + "\n")  # `ensure_ascii`: escribe `"\ud800"`, solo ASCII
    report = auditar(corrida)
    timing = fila(report, "timing")
    assert timing.status == "FAIL"
    assert "no es ISO-8601" in timing.detail
    timing.detail.encode("utf-8")  # no debe lanzar `UnicodeEncodeError`
    render_audit_md(report).encode("utf-8")


# ── run.json como límite inferior ───────────────────────────────────────


def _escribir_run_json(run: Path, inicio: datetime) -> None:
    """Un ``run.json`` mínimo y válido con ``started_utc = inicio`` (el motor aún no lo escribe)."""
    info = RunInfo(
        slug="demo",
        timestamp="20261004-120000",
        started_utc=inicio.isoformat(),
        engine_version="0.8.0",
        python_version="3.11.0",
        max_results=50,
        mailto_set=False,
        status="completed",
    )
    (run / "run.json").write_text(info.model_dump_json(indent=2), encoding="utf-8")


def test_timing_run_json_valido_es_el_limite_inferior_y_pasa(corrida) -> None:
    # `manifest.timestamp` ilegible: si pasara, el límite saldría de `run.json`, no del manifiesto.
    _escribir_run_json(corrida, primera_llamada(corrida) - timedelta(seconds=1))
    edit_yaml(corrida / "manifest.yml", lambda m: m.update(timestamp="TEST"))
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "PASS", timing.detail
    assert "dentro de [inicio, manifiesto]" in timing.detail


def test_timing_marcas_anteriores_al_started_utc_de_run_json_fallan(corrida) -> None:
    # `manifest.timestamp` (el de la corrida real) no falla: el FAIL sale de `run.json`.
    _escribir_run_json(corrida, primera_llamada(corrida) + timedelta(seconds=30))
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "FAIL"
    assert "llm_calls[0] anterior al inicio de la corrida" in timing.detail


def test_timing_run_json_ilegible_se_nombra_como_tal(corrida) -> None:
    (corrida / "run.json").write_text("{\n", encoding="utf-8")
    edit_yaml(corrida / "manifest.yml", lambda m: m.update(timestamp="TEST"))
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "WARN"
    assert "límite inferior no verificable (timestamp `TEST`, run.json ilegible)" in timing.detail


def test_timing_sin_run_json_se_nombra_como_tal(corrida) -> None:
    (corrida / "run.json").unlink(missing_ok=True)
    edit_yaml(corrida / "manifest.yml", lambda m: m.update(timestamp="TEST"))
    timing = fila(auditar(corrida), "timing")
    assert "límite inferior no verificable (timestamp `TEST`, sin run.json)" in timing.detail


# ── response_overlap ────────────────────────────────────────────────────


def test_response_overlap_fake_no_cuenta(corrida) -> None:
    assert fila(auditar(corrida), "response_overlap").status == "PASS"


def test_response_overlap_hashes_de_un_modelo_dentro_de_otro_advierte(corrida) -> None:
    # Síntoma C3: los hashes de respuesta de Sonnet son un subconjunto de los de Opus.
    def _solape(calls: list[dict]) -> None:
        for i, call in enumerate(calls):
            modelo = "opus" if i < 12 else "sonnet"
            call.update(provider="agent", model=modelo, deterministic=False)
            call["response_sha256"] = f"{i % 12:064x}"

    editar_llamadas(corrida, _solape)
    overlap = fila(auditar(corrida), "response_overlap")
    assert overlap.status == "WARN"
    assert "`agent:opus` y `agent:sonnet` comparten 12 de 12 respuestas" in overlap.detail


def test_response_overlap_con_muchos_modelos_compara_solo_los_primeros(corrida) -> None:
    # Una lista hostil con 21 modelos de 10 llamadas haría crecer las parejas al cuadrado:
    # con 10⁵ modelos, el auditor colgaría. Se comparan los 20 primeros y se avisa del resto.
    def _muchos(calls: list[dict]) -> list[dict]:
        nuevas = []
        for i in range(210):
            call = dict(calls[0])
            call.update(provider="agent", model=f"m{i // 10:02d}", deterministic=False)
            call["response_sha256"] = f"{i:064x}"
            nuevas.append(call)
        return nuevas

    editar_llamadas(corrida, _muchos)
    overlap = fila(auditar(corrida), "response_overlap")
    assert overlap.status == "WARN"
    assert "21 modelos" in overlap.detail
    assert "solo se comparan los 20 primeros" in overlap.detail


def _modelos(calls: list[dict], n_modelos: int, *, compartir: tuple[int, int] | None = None):
    """``n_modelos`` modelos no fake de 10 llamadas con hashes propios.

    Con ``compartir=(a, b)``, el modelo ``b`` repite las 10 respuestas del modelo ``a``.
    """
    nuevas = []
    for i in range(n_modelos * 10):
        modelo, orden = divmod(i, 10)
        dueno = compartir[0] if compartir is not None and modelo == compartir[1] else modelo
        call = dict(calls[0])
        call.update(provider="agent", model=f"m{modelo:02d}", deterministic=False)
        call["response_sha256"] = f"{dueno * 10 + orden:064x}"
        nuevas.append(call)
    return nuevas


def test_response_overlap_con_exactamente_20_modelos_sin_solape_pasa(corrida) -> None:
    editar_llamadas(corrida, lambda calls: _modelos(calls, 20))
    overlap = fila(auditar(corrida), "response_overlap")
    assert overlap.status == "PASS", overlap.detail
    assert "20 modelo(s) no fake" in overlap.detail


def test_response_overlap_con_21_modelos_sigue_avisando_del_solape_entre_los_20_primeros(
    corrida,
) -> None:
    editar_llamadas(corrida, lambda calls: _modelos(calls, 21, compartir=(0, 1)))
    overlap = fila(auditar(corrida), "response_overlap")
    assert overlap.status == "WARN"
    assert "`agent:m00` y `agent:m01` comparten 10 de 10 respuestas" in overlap.detail
    assert "solo se comparan los 20 primeros" in overlap.detail


# ── entrada hostil ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "valor",
    [
        pytest.param(None, id="nulo"),
        pytest.param(1_759_000_000, id="entero"),
        pytest.param(["2026-10-04T12:00:00+00:00"], id="lista"),
        pytest.param({"t": "2026-10-04T12:00:00+00:00"}, id="mapa"),
        pytest.param([[[[1] * 9] * 9] * 9] * 9, id="anidado"),
        pytest.param("x" * 50_000, id="cadena-enorme"),
        pytest.param("2026-10-04T12:00:00", id="sin-zona"),
        pytest.param("2026-13-45T00:00:00+00:00", id="fecha-imposible"),
        pytest.param("2026-10-04T12:00:00+00:00\ud800", id="sustituto-suelto"),
    ],
)
def test_parse_utc_acepta_cualquier_objeto_y_devuelve_un_motivo_acotado(valor: object) -> None:
    marca, motivo = parse_utc(valor)
    assert marca is None
    assert motivo is not None
    assert len(motivo) < 200


def test_parse_utc_devuelve_la_marca_con_su_zona() -> None:
    marca, motivo = parse_utc("2026-10-04T12:00:00.5-05:00")
    assert motivo is None
    assert marca is not None
    assert marca.utcoffset() == timedelta(hours=-5)


def test_timing_y_overlap_con_cadenas_de_50_000_caracteres_no_rompen_ni_se_desbordan(
    corrida,
) -> None:
    enorme = "x" * 50_000

    def _hostil(calls: list[dict]) -> None:
        for i, call in enumerate(calls):
            modelo = ("A" if i < 12 else "B") * 50_000
            call.update(provider="agent", model=modelo, deterministic=False)
            call["response_sha256"] = f"{i % 12:064x}"
        calls[0]["timestamp_utc"] = enorme  # marca ilegible
        calls[1].update(provider="p" * 50_000, deterministic=True)  # determinismo, proveedor real

    editar_llamadas(corrida, _hostil)
    edit_ledger(corrida, lambda e: e[0].update(timestamp_utc=enorme))
    edit_yaml(corrida / "manifest.yml", lambda m: m.update(created_utc=enorme))
    report = auditar(corrida)
    timing, overlap = fila(report, "timing"), fila(report, "response_overlap")
    assert timing.status == "FAIL"
    assert overlap.status == "WARN"
    assert len(timing.detail) < 1_000
    assert len(overlap.detail) < 1_000
    assert [c.check_id for c in report.checks if "error interno" in c.detail] == []


def test_timing_con_fechas_en_el_limite_del_calendario_no_desborda(corrida) -> None:
    # `mark ± 2 s` desbordaría en el año 1 o en el 9999 (`OverflowError`): se comparan diferencias.
    def _extremos(entries: list[dict]) -> None:
        entries[0]["timestamp_utc"] = "0001-01-01T00:00:00+00:00"
        entries[1]["timestamp_utc"] = "9999-12-31T23:59:59.999999+00:00"

    edit_ledger(corrida, _extremos)
    edit_yaml(
        corrida / "manifest.yml", lambda m: m.update(created_utc="9999-12-31T23:59:59.999999+00:00")
    )
    report = auditar(corrida)
    timing = fila(report, "timing")
    assert timing.status == "FAIL"
    assert "ledger línea 1 anterior al inicio de la corrida" in timing.detail
    assert "ledger línea 3: retrocede" in timing.detail
    assert [c.check_id for c in report.checks if "error interno" in c.detail] == []


# Una bomba de alias (`*a` nueve veces por nivel, diez niveles) carga en milisegundos, pero
# `str`/`repr` la recorren entera (9**10 hojas): el auditor no puede interpolar ninguno de los
# campos que `timing` y `response_overlap` leen. Corre en un subproceso: si colgara, la sesión
# de pytest no se vería afectada (como en `test_audit_infra.py`).
def test_bomba_de_alias_en_las_marcas_y_los_modelos_no_cuelga_timing_ni_overlap(corrida) -> None:
    llamada = (
        "- {stage: screening_ta, provider: *a9, model: *a9, deterministic: true, "
        "timestamp_utc: *a9, response_sha256: *a9}\n"
    )
    cola = "timestamp: *a9\ncreated_utc: *a9\nllm_calls:\n" + llamada * 12
    (corrida / "run.json").unlink(missing_ok=True)
    (corrida / "manifest.yml").write_text(bomba_de_alias() + cola, encoding="utf-8")
    filas = auditar_en_subproceso(corrida, timeout=60)
    assert filas["timing"][0] == "FAIL"
    assert len(filas["timing"][1]) < 1_000
    assert filas["response_overlap"][0] == "PASS"
    assert [i for i, (_, detalle) in filas.items() if "error interno" in detalle] == []


def test_timing_run_json_que_parsea_pero_no_valida_se_nombra_como_ilegible(corrida) -> None:
    # JSON bien formado y con la forma de un mapa, pero que no es un `RunInfo`: no vale como
    # límite inferior (se cae al `timestamp` del manifiesto, aquí ilegible) y el detalle lo dice.
    (corrida / "run.json").write_text('{"slug": 1}', encoding="utf-8")
    edit_yaml(corrida / "manifest.yml", lambda m: m.update(timestamp="TEST"))
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "WARN"
    assert "límite inferior no verificable (timestamp `TEST`, run.json ilegible)" in timing.detail


def test_timing_run_json_que_no_valida_deja_el_limite_al_timestamp_del_manifiesto(corrida) -> None:
    # Con el `timestamp` del manifiesto sano, un `run.json` roto no impide comprobar el límite.
    (corrida / "run.json").write_text('{"slug": 1}', encoding="utf-8")
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "PASS", timing.detail
    assert "dentro de [inicio, manifiesto]" in timing.detail
