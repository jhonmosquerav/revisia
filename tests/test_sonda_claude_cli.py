"""La sonda del CLI `claude` registra lo que hay sin invocar el CLI real (D11; spec §4.4)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

RUTA = Path(__file__).resolve().parent.parent / "scripts" / "sonda_claude_cli.py"


def _modulo() -> ModuleType:
    spec = importlib.util.spec_from_file_location("sonda_claude_cli", RUTA)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


HELP_NPM = (
    "Usage: claude [options]\n  --json-schema <schema>\n  --max-budget-usd <n>\n"
    "  --bare\n  --tools <list>\n"
)
HOME = str(Path.home())
RUTA_CLI = HOME + "/AppData/Roaming/npm/claude.CMD"
FUGAS = (
    "tok-secreto-123 sk-ant-0123456789abcdefXYZ Bearer bearer-secreto jhon@example.com "
    + HOME
    + "/AppData"
)
HELP_COMPLETO = (
    HELP_NPM
    + "  --safe-mode\n  --max-turns <n>\n  --strict-mcp-config\n  --no-session-persistence\n"
)


def test_el_script_no_importa_revisia_y_corre_en_311() -> None:
    texto = RUTA.read_text(encoding="utf-8")
    assert "import revisia" not in texto and "from revisia" not in texto
    assert "from __future__ import annotations" in texto
    # Sin sintaxis exclusiva de 3.12+: ni `type X =` ni genéricos PEP 695.
    assert "\ntype " not in texto and "def main[" not in texto


def test_detect_flags_distingue_el_shim_npm_del_cli_completo() -> None:
    sonda = _modulo()
    npm = sonda.detect_flags(HELP_NPM)
    assert (npm["--json-schema"], npm["--max-budget-usd"], npm["--bare"], npm["--tools"]) == (
        True,
        True,
        True,
        True,
    )
    assert (npm["--safe-mode"], npm["--max-turns"]) == (False, False)
    assert sonda.detect_flags(HELP_COMPLETO)["--safe-mode"] is True
    assert sonda.detect_flags("--safe-modern")["--safe-mode"] is False  # palabra completa


def test_parse_version() -> None:
    sonda = _modulo()
    assert sonda.parse_version("2.1.126 (Claude Code)") == "2.1.126"
    assert sonda.parse_version("sin versión") is None


def test_locate_structured_en_result_texto_dict_u_otra_clave() -> None:
    sonda = _modulo()
    schema = {
        "required": ["respuesta", "numero"],
        "properties": {"respuesta": {"type": "string"}, "numero": {"type": "integer"}},
    }
    assert sonda.locate_structured({"result": '{"respuesta": "hola", "numero": 7}'}, schema) == {
        "where": "result",
        "valid": True,
    }
    assert sonda.locate_structured({"result": {"respuesta": "hola", "numero": 7}}, schema) == {
        "where": "result",
        "valid": True,
    }
    assert sonda.locate_structured(
        {"result": "texto", "structured_output": {"respuesta": "hola", "numero": 7}}, schema
    ) == {"where": "structured_output", "valid": True}
    assert sonda.locate_structured({"result": '{"respuesta": "hola", "numero": "7"}'}, schema) == {
        "where": "result",
        "valid": False,
    }
    assert sonda.locate_structured({"result": "nada"}, schema) == {"where": None, "valid": False}
    assert sonda.locate_structured("no es json", schema) == {"where": None, "valid": False}


def test_result_meta_lee_subtype_y_coste() -> None:
    sonda = _modulo()
    datos = {"subtype": "error_max_turns", "total_cost_usd": 0.01, "is_error": True}
    assert sonda.result_meta(datos) == datos
    assert sonda.result_meta({"result": "x"}) == {
        "subtype": None,
        "total_cost_usd": None,
        "is_error": None,
    }
    assert sonda.result_meta("no es json") == {
        "subtype": None,
        "total_cost_usd": None,
        "is_error": None,
    }


def test_redact_tapa_tokens_y_valores_del_entorno() -> None:
    sonda = _modulo()
    texto = "Authorization: Bearer abc.def token=sk-ant-0123456789abcdefXYZ otra cosa"
    assert "abc.def" not in sonda.redact(texto, ["abc.def"]) and "sk-ant" not in sonda.redact(
        texto, []
    )
    assert sonda.redact("limpio", ["", None]) == "limpio"


def _fake_run(respuestas: dict[str, subprocess.CompletedProcess | Exception]):
    def _run(cmd, **_kwargs):
        clave = "-p" if "-p" in cmd else cmd[1]
        salida = respuestas[clave]
        if isinstance(salida, Exception):
            raise salida
        return salida

    return _run


def _ok(stdout: str) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


@pytest.mark.parametrize("help_text", [HELP_NPM, HELP_COMPLETO])
def test_main_escribe_el_informe_y_solo_usa_safe_mode_si_se_anuncia(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, help_text: str
) -> None:
    sonda = _modulo()
    comandos: list[list[str]] = []
    respuestas = {
        "--version": _ok("2.1.126 (Claude Code)"),
        "--help": _ok(help_text),
        "-p": subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(
                {
                    "subtype": "success",
                    "result": '{"respuesta": "hola", "numero": 7}',
                    "total_cost_usd": 0.0,
                    "usage": {},
                    "nota": FUGAS,
                }
            ),
            stderr=FUGAS,
        ),
    }
    fake = _fake_run(respuestas)

    def _run(cmd, **kwargs):
        comandos.append(list(cmd))
        return fake(cmd, **kwargs)

    monkeypatch.setattr(sonda.subprocess, "run", _run)
    monkeypatch.setattr(sonda.shutil, "which", lambda _c: RUTA_CLI)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok-secreto-123")
    out = tmp_path / "sondas" / "x.md"
    assert sonda.main(["--out", str(out), "--model", "sonnet"]) == 0
    informe = out.read_text(encoding="utf-8")
    llamadas_p = [c for c in comandos if "-p" in c]
    llamada = llamadas_p[0]
    assert ("--safe-mode" in llamada) is ("--safe-mode" in help_text)
    con_max_turns = "--max-turns" in help_text
    assert len(llamadas_p) == (2 if con_max_turns else 1)
    assert "--max-turns" not in llamada
    if con_max_turns:
        assert llamadas_p[1][llamadas_p[1].index("--max-turns") + 1] == "1"
        assert "MAX_TURNS con --json-schema: compatible" in informe
    else:
        assert "no se lanzó: el CLI no anuncia --max-turns" in informe
        assert "MAX_TURNS con --json-schema: no anunciado" in informe
    assert "- subtype: `success`" in informe and "- total_cost_usd: 0.0" in informe
    assert "## Segunda llamada: --max-turns 1" in informe
    assert "--json-schema" in llamada and "--bare" not in llamada
    assert "--tools" in llamada and llamada[llamada.index("--tools") + 1] == ""
    assert "2.1.126" in informe and "## Dónde viene el objeto validado" in informe
    assert "`result`" in informe and "válido: sí" in informe
    for fuga in (
        "tok-secreto-123",
        "sk-ant-0123456789abcdefXYZ",
        "bearer-secreto",
        "jhon@example.com",
        str(Path.home()),
        "AppData/Roaming",
    ):
        assert fuga not in informe
    assert "<redacted>" in informe and "<correo>" in informe
    esperado = "MIN_CLI_VERSION candidata: 2.1.126" if "--safe-mode" in help_text else "no sirve"
    assert esperado in informe


def test_main_con_cli_ausente_o_json_invalido_escribe_el_informe_igual(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sonda = _modulo()
    monkeypatch.setattr(sonda.shutil, "which", lambda _c: None)
    monkeypatch.setattr(
        sonda.subprocess,
        "run",
        _fake_run(
            {
                "--version": FileNotFoundError("claude"),
                "--help": FileNotFoundError("claude"),
                "-p": FileNotFoundError("claude"),
            }
        ),
    )
    out = tmp_path / "a.md"
    assert sonda.main(["--out", str(out)]) == 0
    assert "FileNotFoundError" in out.read_text(encoding="utf-8")

    monkeypatch.setattr(sonda.shutil, "which", lambda _c: "/usr/bin/claude")
    monkeypatch.setattr(
        sonda.subprocess,
        "run",
        _fake_run(
            {
                "--version": _ok("2.1.300"),
                "--help": _ok(HELP_COMPLETO),
                "-p": _ok("esto no es JSON {"),
            }
        ),
    )
    out2 = tmp_path / "b.md"
    assert sonda.main(["--out", str(out2)]) == 0
    informe = out2.read_text(encoding="utf-8")
    seccion = informe.split("## stdout crudo")[1].split("## stderr")[0]
    assert "```text" in seccion and "válido: no" in informe


def test_el_informe_no_filtra_la_ruta_resuelta_del_cli_ni_en_el_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sonda = _modulo()
    monkeypatch.setattr(sonda.shutil, "which", lambda _c: RUTA_CLI)
    timeout = subprocess.TimeoutExpired(cmd=[RUTA_CLI, "-p"], timeout=1)
    monkeypatch.setattr(
        sonda.subprocess,
        "run",
        _fake_run({"--version": timeout, "--help": _ok(HELP_COMPLETO), "-p": timeout}),
    )
    out = tmp_path / "t.md"
    assert sonda.main(["--out", str(out)]) == 0
    informe = out.read_text(encoding="utf-8")
    assert "TimeoutExpired" in informe
    assert HOME not in informe and "AppData" not in informe
    assert "claude.CMD" in informe


def test_redact_sustituye_el_home_y_los_correos() -> None:
    sonda = _modulo()
    home = str(Path.home())
    salida = sonda.redact(f"{home}/x y {home.replace(chr(92), chr(92) * 2)} a.b@c.org", [])
    assert home not in salida and "a.b@c.org" not in salida
    assert "~/x" in salida and "<correo>" in salida


def test_main_por_defecto_escribe_en_docs_superpowers_sondas_con_la_fecha(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sonda = _modulo()
    monkeypatch.setattr(sonda, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(sonda.shutil, "which", lambda _c: None)
    monkeypatch.setattr(
        sonda.subprocess,
        "run",
        _fake_run(
            {
                "--version": FileNotFoundError(),
                "--help": FileNotFoundError(),
                "-p": FileNotFoundError(),
            }
        ),
    )
    assert sonda.main([]) == 0
    ficheros = list((tmp_path / "docs" / "superpowers" / "sondas").glob("*-claude-cli.md"))
    assert len(ficheros) == 1 and len(ficheros[0].name) == len("2026-10-18-claude-cli.md")


def test_el_script_corre_como_proceso_con_help() -> None:
    proc = subprocess.run(
        [sys.executable, "-I", str(RUTA), "--help"], capture_output=True, text=True, timeout=60
    )
    assert proc.returncode == 0
    for opcion in ("--cli", "--model", "--out", "--timeout"):
        assert opcion in proc.stdout
