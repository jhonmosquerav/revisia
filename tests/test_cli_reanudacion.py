"""`revisia run --resume` y códigos de salida de una corrida (Ola 1, D3, D13 y D14;
spec 2026-10-04 §7)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml
from fakes import fetch_disponible

from revisia import cli
from revisia.config import load_protocol
from revisia.llm import preflight as preflight_mod
from revisia.memory import ResearchBrain
from revisia.orchestration.pipeline import run_pipeline
from revisia.orchestration.run_context import RunContext, RunInterrupted
from revisia.orchestration.snapshot import read_run_info
from revisia.schemas.records import SearchRecord

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "demo-mini-review"


@pytest.fixture(autouse=True)
def entorno(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sin .env real y con httpx "instalado" para el preflight del demo (M6)."""
    monkeypatch.setattr(cli, "_load_dotenv", lambda: None)
    monkeypatch.setattr(preflight_mod, "_default_find_spec", lambda _name: object())


def _busqueda(query: str, n: int) -> list[SearchRecord]:
    # Sin DOI, PMCID ni oa_url: al reanudar desde el CLI la recuperación no toca la red.
    return [
        SearchRecord(record_id="rec-1", title="LLM screening", source_db="OpenAlex"),
        SearchRecord(record_id="rec-2", title="Active learning", source_db="OpenAlex"),
    ][:n]


def _corrida_en_pausa(tmp_path: Path, proto: Path = EXAMPLE) -> Path:
    protocol = load_protocol(proto)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")
    assert run_pipeline(protocol, proto, ctx, search_fn=_busqueda).status == "paused"
    return ctx.run_dir


def _estado(carpeta: Path) -> dict[str, bytes]:
    """Instantánea byte a byte de una carpeta: ruta relativa → contenido."""
    return {
        p.relative_to(carpeta).as_posix(): p.read_bytes() for p in carpeta.rglob("*") if p.is_file()
    }


def test_cli_run_resume_reanuda_la_misma_carpeta(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    run_dir = _corrida_en_pausa(tmp_path)

    rc = cli.main(["run", "--resume", str(run_dir), "--auto-approve", "--max", "99"])

    out = capsys.readouterr().out
    assert rc == 0
    assert "COMPLETED" in out
    assert "--max 99 se ignora al reanudar" in out
    assert sorted(p.name for p in (tmp_path / "runs").iterdir()) == [run_dir.name]
    info = read_run_info(run_dir)
    assert (info.status, len(info.resumes), info.max_results) == ("completed", 1, 25)


def test_cli_resume_avisa_si_falta_mailto(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")
    run_pipeline(protocol, EXAMPLE, ctx, search_fn=_busqueda, mailto="revisora@example.org")
    assert cli.main(["run", "--resume", str(ctx.run_dir)]) == 0
    assert "empezó con --mailto" in capsys.readouterr().out


def test_cli_resume_no_avisa_de_mailto_si_no_hace_falta(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    # Sin --mailto en el origen (nada que repetir) y con --mailto de nuevo: sin aviso.
    sin_correo = _corrida_en_pausa(tmp_path)
    assert cli.main(["run", "--resume", str(sin_correo)]) == 0
    assert "empezó con --mailto" not in capsys.readouterr().out

    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path / "otras", "T")
    run_pipeline(protocol, EXAMPLE, ctx, search_fn=_busqueda, mailto="revisora@example.org")
    assert cli.main(["run", "--resume", str(ctx.run_dir), "--mailto", "revisora@example.org"]) == 0
    assert "empezó con --mailto" not in capsys.readouterr().out


def test_cli_pausa_dice_como_reanudar(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    run_dir = _corrida_en_pausa(tmp_path)
    assert cli.main(["run", "--resume", str(run_dir)]) == 0
    assert f"Reanuda con: revisia run --resume {run_dir}" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("error", "rc", "esperado"),
    [
        ("interrupcion", 3, "revisia run --resume"),
        ("ctrl_c", 130, "Ctrl+C"),
    ],
)
def test_cli_interrupcion_rc_3_con_instrucciones(
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    error: str,
    rc: int,
    esperado: str,
) -> None:
    run_dir = tmp_path / "runs" / "demo-mini-review-T"

    def _falla(*_a, **_k):
        if error == "ctrl_c":
            raise KeyboardInterrupt
        raise RunInterrupted(run_dir, "screening_ta", "RuntimeError: 429 Too Many Requests")

    monkeypatch.setattr("revisia.orchestration.flow.run_review", _falla)
    assert cli.main(["run", str(EXAMPLE)]) == rc
    err = capsys.readouterr().err
    assert esperado in err
    assert "Traceback" not in err
    if error == "interrupcion":
        assert f"revisia run --resume {run_dir}" in err


def test_resume_de_corrida_anterior_a_la_ola_1_sale_2(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    antigua = tmp_path / "runs" / "demo-20260901-120000"
    (antigua / "03_screening").mkdir(parents=True)
    (antigua / "manifest.yml").write_text("slug: demo\n", encoding="utf-8")

    rc = cli.main(["run", "--resume", str(antigua)])

    err = capsys.readouterr().err
    assert rc == 2
    assert "anterior a la Ola 1" in err
    assert "revisia run <protocolo>" in err


def test_resume_con_protocolo_modificado_sale_2(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    proto = tmp_path / "proto"
    shutil.copytree(EXAMPLE, proto)
    run_dir = _corrida_en_pausa(tmp_path, proto)
    criterios = proto / "inclusion_exclusion.yml"
    criterios.write_text(criterios.read_text(encoding="utf-8") + "\n# nuevo criterio\n", "utf-8")

    rc = cli.main(["run", str(proto), "--resume", str(run_dir)])

    err = capsys.readouterr().err
    assert rc == 2
    assert "no coinciden" in err and "inclusion_exclusion.yml" in err
    assert read_run_info(run_dir).resumes == []  # no se tocó la corrida


def test_cli_run_sin_protocolo_ni_resume_sale_2(capsys: pytest.CaptureFixture) -> None:
    assert cli.main(["run"]) == 2
    assert "--resume" in capsys.readouterr().err


def test_brain_no_sedimenta_dos_veces(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")
    run_pipeline(
        protocol, EXAMPLE, ctx, auto_approve=True, search_fn=_busqueda, fetch_fn=fetch_disponible
    )
    cerebro = tmp_path / "cerebro"
    assert not ResearchBrain(cerebro).has_run("demo-mini-review", "T")

    for _ in range(2):  # reanudar una corrida completada no la duplica en el cerebro
        assert cli.main(["run", "--resume", str(ctx.run_dir), "--brain", str(cerebro)]) == 0

    eventos = (cerebro / "genome" / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(e)["timestamp"] for e in eventos] == ["T"]
    assert ResearchBrain(cerebro).has_run("demo-mini-review", "T")
    assert "ya estaba sedimentada" in capsys.readouterr().out


def test_brain_ya_sedimentada_no_pisa_el_flow_de_actualizacion(tmp_path: Path) -> None:
    # `prior` ya incluye una corrida sedimentada: reescribir el flow "contra sí misma"
    # pisaría el que se generó cuando esa corrida se completó contra la anterior.
    protocol = load_protocol(EXAMPLE)
    for timestamp in ("A", "B"):
        ctx = RunContext(protocol.slug, tmp_path / "runs", timestamp)
        run_pipeline(
            protocol,
            EXAMPLE,
            ctx,
            auto_approve=True,
            search_fn=_busqueda,
            fetch_fn=fetch_disponible,
        )
    cerebro = tmp_path / "cerebro"
    corrida_a = tmp_path / "runs" / "demo-mini-review-A"
    corrida_b = tmp_path / "runs" / "demo-mini-review-B"
    assert cli.main(["run", "--resume", str(corrida_a), "--brain", str(cerebro)]) == 0
    assert cli.main(["run", "--resume", str(corrida_b), "--brain", str(cerebro)]) == 0
    flow = corrida_b / "deliverable" / "prisma_flow_updated.md"
    assert flow.exists()  # B se sedimentó como actualización de A
    marcado = flow.read_text(encoding="utf-8") + "\n<!-- generado en la primera finalización -->\n"
    flow.write_text(marcado, encoding="utf-8")

    assert cli.main(["run", "--resume", str(corrida_b), "--brain", str(cerebro)]) == 0

    assert flow.read_text(encoding="utf-8") == marcado


# ── Requisitos de revisiones anteriores (más allá del brief) ─────────────────────────────


@pytest.mark.parametrize(
    "contenido",
    [
        b'{"slug": "demo-mini-review", "timestamp": "T"',  # JSON truncado (caída a mitad)
        b"{}",  # JSON válido que no es un run.json
        b"",  # fichero vacío
        b"\xff\xfe\x00\x9c basura binaria",  # ni siquiera es UTF-8
    ],
    ids=["truncado", "sin-campos", "vacio", "binario"],
)
def test_cli_resume_con_run_json_danado_sale_2_sin_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture, contenido: bytes
) -> None:
    run_dir = _corrida_en_pausa(tmp_path)
    (run_dir / "run.json").write_bytes(contenido)
    antes = _estado(run_dir)

    rc = cli.main(["run", "--resume", str(run_dir)])

    err = capsys.readouterr().err
    assert rc == 2
    assert "run.json" in err and "revisia run <protocolo>" in err
    assert "Traceback" not in err
    assert _estado(run_dir) == antes  # no se tocó nada de la corrida


def test_cli_resume_con_protocolo_de_la_corrida_danado_sale_2(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    run_dir = _corrida_en_pausa(tmp_path)
    (run_dir / "00_protocol" / "protocol.yml").write_text("title: [sin cerrar\n", encoding="utf-8")

    rc = cli.main(["run", "--resume", str(run_dir)])

    err = capsys.readouterr().err
    assert rc == 2
    assert "00_protocol" in err
    assert "Traceback" not in err


def test_cli_resume_preflight_falla_sin_tocar_la_corrida(
    tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    # D10: el preflight va antes de tocar nada. El protocolo de la corrida pasa a pedir un
    # proveedor sin API key: debe salir el error del preflight (no "no coinciden", que es
    # el siguiente paso) y la carpeta de la corrida y el cerebro quedar intactos.
    run_dir = _corrida_en_pausa(tmp_path)
    snapshot = run_dir / "00_protocol" / "protocol.yml"
    snapshot.write_text(
        snapshot.read_text(encoding="utf-8").replace("provider: fake", "provider: openrouter"),
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    antes = _estado(run_dir)
    cerebro = tmp_path / "cerebro"

    rc = cli.main(["run", "--resume", str(run_dir), "--brain", str(cerebro)])

    err = capsys.readouterr().err
    assert rc == 2
    assert "OPENROUTER_API_KEY" in err
    assert "no coinciden" not in err and "Traceback" not in err
    assert _estado(run_dir) == antes
    assert not cerebro.exists()


def test_cli_resume_de_carpeta_inexistente_sale_2_sin_crearla(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    inexistente = tmp_path / "runs" / "no-existe"

    assert cli.main(["run", "--resume", str(inexistente)]) == 2

    assert "no existe" in capsys.readouterr().err
    assert not inexistente.exists() and not (tmp_path / "runs").exists()


def test_cli_resume_con_carpeta_de_protocolo_inexistente_sale_2(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    run_dir = _corrida_en_pausa(tmp_path)

    rc = cli.main(["run", str(tmp_path / "no-hay-protocolo"), "--resume", str(run_dir)])

    assert rc == 2
    assert "no existe" in capsys.readouterr().err
    assert read_run_info(run_dir).resumes == []


# ── Pulido de la pista C: sin tracebacks ni mensajes engañosos (revisión de B15, B16, B17) ──


@pytest.mark.parametrize("contenido", ["- a\n", "hola\n"], ids=["lista", "escalar"])
@pytest.mark.parametrize("modo", ["validate", "run", "resume"])
def test_protocol_yml_que_no_es_un_mapa_sale_2_sin_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture, modo: str, contenido: str
) -> None:
    # `load_protocol` hacía `raw.setdefault(...)` sobre una lista o un escalar y lanzaba
    # AttributeError (traceback), también con `--resume`.
    proto = tmp_path / "proto"
    shutil.copytree(EXAMPLE, proto)
    if modo == "resume":
        run_dir = _corrida_en_pausa(tmp_path)
        (run_dir / "00_protocol" / "protocol.yml").write_text(contenido, encoding="utf-8")
        argv = ["run", "--resume", str(run_dir)]
    else:
        (proto / "protocol.yml").write_text(contenido, encoding="utf-8")
        argv = [modo, str(proto)]

    rc = cli.main(argv)

    err = capsys.readouterr().err
    assert rc == 2
    assert "Traceback" not in err and "AttributeError" not in err
    assert "ReviewProtocol" in err  # la ValidationError real, no un traceback


def test_error_de_otro_fichero_no_se_atribuye_a_run_json(
    tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    # El handler decía siempre «(run.json o 00_protocol/)… empieza una corrida nueva», aunque
    # el error viniera de otro sitio (p. ej. el manifiesto, al sedimentar en el cerebro con
    # la corrida ya completada). Ahora cita el error real, recortado y sin secretos, y
    # condiciona el consejo al fichero.
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")
    run_pipeline(
        protocol, EXAMPLE, ctx, auto_approve=True, search_fn=_busqueda, fetch_fn=fetch_disponible
    )

    def _manifiesto_roto(self, run_dir):
        raise yaml.YAMLError("manifest.yml ilegible api_key=SECRETO123 " + "x" * 1000)

    monkeypatch.setattr(ResearchBrain, "record_from_run", _manifiesto_roto)

    rc = cli.main(["run", "--resume", str(ctx.run_dir), "--brain", str(tmp_path / "cerebro")])

    err = capsys.readouterr().err
    assert rc == 2
    assert "YAMLError: manifest.yml ilegible" in err  # tipo y primera línea del error real
    assert "SECRETO123" not in err and "api_key=<redacted>" in err
    assert max(len(linea) for linea in err.splitlines()) < 400  # recortado a ~300
    assert "Si el fichero es run.json o está en 00_protocol/, la corrida no es reanudable" in err
    assert "(run.json o 00_protocol/)" not in err  # ya no lo afirma sin condición


def test_error_de_run_json_nombra_el_modelo_que_no_valida(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    run_dir = _corrida_en_pausa(tmp_path)
    (run_dir / "run.json").write_text("{}", encoding="utf-8")

    assert cli.main(["run", "--resume", str(run_dir)]) == 2

    err = capsys.readouterr().err
    assert "ValidationError" in err and "RunInfo" in err
    assert "la corrida no es reanudable: empieza una nueva con `revisia run <protocolo>`" in err


def _excepciones_de_la_corrida(tmp_path: Path) -> list:
    """Una instancia real de cada excepción que ``_run_guarded`` traduce, con su rc."""
    from revisia.llm.preflight import PreflightError, PreflightIssue, PreflightReport
    from revisia.orchestration.hitl import DecisionFileError
    from revisia.orchestration.journal import JournalError
    from revisia.orchestration.run_context import LegacyRunError, RunDirExistsError
    from revisia.orchestration.snapshot import ProtocolMismatchError

    informe = PreflightReport(issues=(PreflightIssue("error", "llm.default", "sin API key"),))
    return [
        (JournalError("diario corrupto"), 2),
        (RunDirExistsError(f"{tmp_path} ya existe"), 2),
        (ProtocolMismatchError("no coinciden", ["protocol.yml"]), 2),
        (LegacyRunError(f"{tmp_path}: corrida anterior a la Ola 1"), 2),
        (DecisionFileError("decision.yml ilegible"), 2),
        (PreflightError(informe), 2),
        (FileNotFoundError("No se encontró protocol.yml"), 2),
        (RunInterrupted(tmp_path, "screening_ta", "RuntimeError: 429"), 3),
        (KeyboardInterrupt(), 130),
    ]


@pytest.mark.parametrize("indice", range(9), ids=lambda i: f"caso{i}")
def test_run_guarded_traduce_cada_excepcion_en_su_codigo(
    tmp_path: Path, capsys: pytest.CaptureFixture, indice: int
) -> None:
    excepcion, esperado = _excepciones_de_la_corrida(tmp_path)[indice]

    def _falla() -> int:
        raise excepcion

    assert cli._run_guarded(_falla) == esperado

    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert err.strip()  # siempre dice algo


def test_brain_ya_sedimentada_no_dice_que_se_registrara(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    # Reanudar una corrida ya sedimentada imprimía «se registrará como actualización» y
    # después «ya estaba sedimentada»: dos mensajes contradictorios.
    protocol = load_protocol(EXAMPLE)
    cerebro = tmp_path / "cerebro"
    for timestamp in ("A", "B"):
        ctx = RunContext(protocol.slug, tmp_path / "runs", timestamp)
        run_pipeline(
            protocol,
            EXAMPLE,
            ctx,
            auto_approve=True,
            search_fn=_busqueda,
            fetch_fn=fetch_disponible,
        )
    corrida_a = tmp_path / "runs" / "demo-mini-review-A"
    corrida_b = tmp_path / "runs" / "demo-mini-review-B"
    assert cli.main(["run", "--resume", str(corrida_a), "--brain", str(cerebro)]) == 0
    capsys.readouterr()

    # B es nueva para el cerebro, que ya conoce el slug: se registrará como actualización.
    assert cli.main(["run", "--resume", str(corrida_b), "--brain", str(cerebro)]) == 0
    primera = capsys.readouterr().out
    assert "se registrará como actualización" in primera
    assert "ya estaba sedimentada" not in primera

    # Reanudar B otra vez: ya está sedimentada.
    assert cli.main(["run", "--resume", str(corrida_b), "--brain", str(cerebro)]) == 0
    segunda = capsys.readouterr().out
    assert "ya estaba sedimentada" in segunda
    assert "se registrará como actualización" not in segunda
    assert "Memoria previa: 2 corrida(s)" in segunda


def test_cli_resume_avisa_de_que_runs_root_no_aplica(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    run_dir = _corrida_en_pausa(tmp_path)

    assert cli.main(["run", "--resume", str(run_dir), "--runs-root", str(tmp_path / "otra")]) == 0

    out = capsys.readouterr().out
    assert f"--runs-root no aplica al reanudar: la corrida vive en {run_dir}" in out
    assert not (tmp_path / "otra").exists()  # y no se crea nada ahí

    # Sin la opción, o con su valor por defecto, no hay aviso.
    for extra in ([], ["--runs-root", "runs"]):
        assert cli.main(["run", "--resume", str(run_dir), *extra]) == 0
        assert "--runs-root" not in capsys.readouterr().out
