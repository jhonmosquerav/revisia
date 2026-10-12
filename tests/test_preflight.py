"""Preflight sin red de una corrida (auditoría 2026-09-03, M6; spec 2026-10-04 §5).

Todos con ``env``, ``find_spec`` y ``which`` falsos: no dependen del venv.
"""

from __future__ import annotations

import importlib
import inspect
import tomllib
from datetime import date
from pathlib import Path

import pytest

from revisia.config import ReviewProtocol
from revisia.llm.preflight import (
    PROVIDER_REQUIREMENTS,
    PreflightError,
    PreflightIssue,
    PreflightReport,
    check_retired,
    preflight,
    stages_in_use,
)
from revisia.llm.providers.agent import use_agent_callback
from revisia.llm.registry import _BUILDERS, available_providers

ROOT = Path(__file__).resolve().parent.parent
HOY = date(2026, 10, 4)


def _todo_instalado(_name: str) -> object:
    return object()


def _con_claude(_name: str) -> str:
    return "/usr/local/bin/claude"


def _sin_binario(_name: str) -> None:
    return None


def _proto(**overrides) -> ReviewProtocol:
    raw = {
        "slug": "demo",
        "title": "Demo",
        "question": {"text": "¿X afecta Y?", "framework": "PEO", "components": {"P": "x"}},
        "databases": ["OpenAlex"],
        "llm": {"default": {"provider": "fake", "model": "fake-1"}},
    }
    raw.update(overrides)
    return ReviewProtocol.model_validate(raw)


@pytest.fixture()
def proto_dir(tmp_path: Path) -> Path:
    (tmp_path / "search_strings").mkdir()
    (tmp_path / "search_strings" / "openalex.txt").write_text("llm AND screening", "utf-8")
    return tmp_path


def _run(protocol: ReviewProtocol, proto_dir: Path, **kwargs) -> PreflightReport:
    kwargs.setdefault("context", "validate")
    kwargs.setdefault("env", {})
    kwargs.setdefault("find_spec", _todo_instalado)
    kwargs.setdefault("which", _con_claude)
    kwargs.setdefault("today", HOY)
    return preflight(protocol, proto_dir, **kwargs)


def _messages(issues: tuple[PreflightIssue, ...]) -> str:
    return "\n".join(f"[{i.where}] {i.message}" for i in issues)


# ── Deriva entre la tabla y el código ───────────────────────────────────


def test_preflight_cubre_todos_los_proveedores_del_registro() -> None:
    assert set(PROVIDER_REQUIREMENTS) == set(available_providers())
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    extras = pyproject["project"]["optional-dependencies"]
    for name, req in PROVIDER_REQUIREMENTS.items():
        if req.extra is not None:
            assert req.extra in extras, f"{name}: extra {req.extra!r} inexistente"


def test_preflight_env_key_coincide_con_la_del_proveedor() -> None:
    for name, req in PROVIDER_REQUIREMENTS.items():
        module_path, class_name = _BUILDERS[name]
        cls = getattr(importlib.import_module(module_path), class_name)
        if name == "gemini":
            # GeminiProvider no tiene `env_key`: lee el literal (gemini.py:43).
            assert f'os.environ.get("{req.env_var}")' in inspect.getsource(cls)
        elif req.env_var is not None:
            assert cls.env_key == req.env_var, name
    # local_openai tiene env_key, pero su key es opcional: no se exige.
    assert PROVIDER_REQUIREMENTS["local_openai"].env_var is None


# ── Proveedores ──────────────────────────────────────────────────────────


def test_preflight_sdk_ausente_es_error_con_extra_sugerido(proto_dir: Path) -> None:
    protocol = _proto(llm={"default": {"provider": "openai", "model": "gpt-5"}})
    report = _run(
        protocol,
        proto_dir,
        env={"OPENAI_API_KEY": "sk-x"},
        find_spec=lambda name: None if name == "openai" else object(),
    )
    assert not report.ok
    assert "uv sync --extra openai" in _messages(report.errors)


def test_preflight_paquete_padre_ausente_no_revienta(proto_dir: Path) -> None:
    def find_spec(name: str) -> object:
        if name == "google.genai":
            raise ModuleNotFoundError("No module named 'google'")
        return object()

    protocol = _proto(llm={"default": {"provider": "gemini", "model": "gemini-3.5-flash-lite"}})
    report = _run(protocol, proto_dir, env={"GEMINI_API_KEY": "k"}, find_spec=find_spec)
    assert "uv sync --extra gemini" in _messages(report.errors)


def test_preflight_key_ausente_es_error(proto_dir: Path) -> None:
    protocol = _proto(llm={"default": {"provider": "gemini", "model": "gemini-3.5-flash-lite"}})
    sin_key = _run(protocol, proto_dir, env={"GEMINI_API_KEY": ""})
    errores = [i for i in sin_key.errors if "GEMINI_API_KEY" in i.message]
    # Mismo proveedor en las cinco etapas: un solo error que las nombra todas.
    assert len(errores) == 1
    assert "screening_ft" in errores[0].where and "sintesis" in errores[0].where
    assert _run(protocol, proto_dir, env={"GEMINI_API_KEY": "k"}).ok


def test_preflight_local_openai_no_exige_key(proto_dir: Path) -> None:
    protocol = _proto(llm={"default": {"provider": "local_openai", "model": "llama3.1:8b"}})
    assert _run(protocol, proto_dir, env={}).ok


def test_preflight_claude_code_sin_binario_es_error(proto_dir: Path) -> None:
    protocol = _proto(llm={"default": {"provider": "claude_code", "model": "sonnet"}})
    report = _run(protocol, proto_dir, which=_sin_binario)
    assert "'claude'" in _messages(report.errors)
    assert _run(protocol, proto_dir, which=_con_claude).ok


def test_preflight_agent_sin_callback_error_en_run_aviso_en_validate(proto_dir: Path) -> None:
    protocol = _proto(llm={"default": {"provider": "agent", "model": "session-agent"}})
    en_validate = _run(protocol, proto_dir, context="validate")
    assert en_validate.ok
    assert "callback" in _messages(en_validate.warnings)
    for context in ("run", "resume"):
        report = _run(protocol, proto_dir, context=context, mailto="x@y.z")
        assert "callback" in _messages(report.errors), context
    with use_agent_callback(lambda _req, _schema: {}):
        assert _run(protocol, proto_dir, context="run", mailto="x@y.z").ok


def test_preflight_effort_fuera_de_claude_code_es_error(proto_dir: Path) -> None:
    protocol = _proto(
        llm={"default": {"provider": "gemini", "model": "gemini-3.5-flash-lite", "effort": "high"}}
    )
    report = _run(protocol, proto_dir, env={"GEMINI_API_KEY": "k"})
    assert "effort='high'" in _messages(report.errors)


def test_preflight_proveedor_desconocido_es_error(proto_dir: Path) -> None:
    protocol = _proto(llm={"default": {"provider": "gemni", "model": "x"}})
    report = _run(protocol, proto_dir)
    assert "proveedor desconocido 'gemni'" in _messages(report.errors)
    exc = PreflightError(report)
    assert exc.report is report
    assert "gemni" in str(exc)


def test_preflight_etapa_sin_proveedor_ni_default_es_error(proto_dir: Path) -> None:
    # M6: hoy un FT sin proveedor se descubre tras gastar el cribado T/A.
    protocol = _proto(llm={"screening_ta": {"provider": "fake", "model": "fake-1"}})
    report = _run(protocol, proto_dir)
    wheres = {i.where for i in report.errors}
    assert {"screening_ft", "extraccion", "rob", "sintesis"} <= wheres
    assert "screening_ta" not in wheres
    assert [w for w, _ in stages_in_use(protocol)] == ["screening_ta"]


def test_preflight_revisa_ensemble_y_segundo_extractor(proto_dir: Path) -> None:
    protocol = _proto(
        ensemble=["screening_ta"],
        ensemble_llm={
            "screening_ta": [
                {"provider": "fake", "model": "fake-a"},
                {"provider": "openai", "model": "gpt-5"},
            ],
            "extraccion": [
                {"provider": "anthropic", "model": "claude-x"},
                {"provider": "gemini", "model": "gemini-3.5-flash-lite"},
            ],
        },
    )
    report = _run(protocol, proto_dir, env={})
    errores = _messages(report.errors)
    assert "[screening_ta[1]]" in errores and "OPENAI_API_KEY" in errores
    assert "[extraccion_2]" in errores and "ANTHROPIC_API_KEY" in errores
    assert "GEMINI_API_KEY" not in errores  # el 2.º miembro de extracción no se usa
    assert "solo se usa el primero" in _messages(report.warnings)


def test_preflight_modelo_retirado_es_error_y_futuro_aviso() -> None:
    retirado = _proto(llm={"default": {"provider": "fake", "model": "gemini-2.0-flash"}})
    assert check_retired(retirado, HOY)[0].level == "error"
    futuro = _proto(llm={"default": {"provider": "fake", "model": "gemini-3.1-flash-lite"}})
    aviso = check_retired(futuro, HOY)
    assert aviso[0].level == "warning" and "2027-05-07" in aviso[0].message


# ── Bases y búsqueda ─────────────────────────────────────────────────────


def _sin_httpx(name: str) -> object | None:
    return None if name == "httpx" else object()


def test_preflight_base_desconocida_es_error(proto_dir: Path) -> None:
    report = _run(_proto(databases=["OpenAlex", "Scopuss"]), proto_dir)
    assert "base desconocida 'Scopuss'" in _messages(report.errors)


@pytest.mark.parametrize(
    "db",
    [
        "CINAHL",
        "Cochrane",
        "Cochrane Library",
        "CENTRAL",
        "ProQuest",
        "EconLit",
        "JSTOR",
        "IEEE Xplore",
        "ACM",
        "ScienceDirect",
        "EBSCO",
        "Ovid",
    ],
)
def test_preflight_bases_de_suscripcion_son_manuales(proto_dir: Path, db: str) -> None:
    report = _run(_proto(databases=["OpenAlex", db]), proto_dir)
    assert report.ok, _messages(report.errors)


def test_preflight_manual_sin_imported_avisa(proto_dir: Path) -> None:
    protocol = _proto(databases=["OpenAlex", "Scopus"])
    assert "imported/" in _messages(_run(protocol, proto_dir).warnings)
    (proto_dir / "imported").mkdir()
    (proto_dir / "imported" / "scopus.ris").write_text("TY  - JOUR\nER  -\n", "utf-8")
    assert "imported/" not in _messages(_run(protocol, proto_dir).warnings)


def test_preflight_backend_sin_cadena_avisa(proto_dir: Path) -> None:
    (proto_dir / "search_strings" / "europepmc.txt").write_text("   \n", "utf-8")
    protocol = _proto(databases=["OpenAlex", "Crossref", "Europe PMC"])
    avisos = _messages(_run(protocol, proto_dir).warnings)
    assert "search_strings/crossref.txt" in avisos
    assert "search_strings/europepmc.txt" in avisos  # vacío cuenta como ausente
    assert "search_strings/openalex.txt" not in avisos


def test_preflight_databases_vacio_avisa_openalex(proto_dir: Path) -> None:
    avisos = _messages(_run(_proto(databases=[]), proto_dir).warnings)
    assert "OpenAlex" in avisos


def test_preflight_httpx_ausente_es_error_con_bases_con_backend(proto_dir: Path) -> None:
    report = _run(_proto(databases=["OpenAlex"]), proto_dir, find_spec=_sin_httpx)
    assert "uv sync --extra search" in _messages(report.errors)
    # Solo bases manuales: no hay búsqueda programática, pero todo quedará como
    # no recuperado → aviso, no error.
    (proto_dir / "imported").mkdir()
    (proto_dir / "imported" / "wos.ris").write_text("TY  - JOUR\nER  -\n", "utf-8")
    solo_manual = _run(_proto(databases=["Web of Science"]), proto_dir, find_spec=_sin_httpx)
    assert solo_manual.ok
    assert "no recuperados" in _messages(solo_manual.warnings)


def test_preflight_sin_mailto_avisa(proto_dir: Path) -> None:
    assert "--mailto" in _messages(_run(_proto(), proto_dir, context="run").warnings)
    assert "--mailto" not in _messages(
        _run(_proto(), proto_dir, context="run", mailto="x@y.z").warnings
    )
    assert "--mailto" not in _messages(_run(_proto(), proto_dir, context="validate").warnings)


def test_preflight_resume_salta_bases_y_busqueda(proto_dir: Path) -> None:
    # Al reanudar, la búsqueda está congelada en 01_search/: ni bases ni httpx.
    report = _run(_proto(databases=["Scopuss"]), proto_dir, context="resume", find_spec=_sin_httpx)
    assert report.ok


# ── Corrección de revisión: cadenas ilegibles, imported/ y consejo de base ──


def test_preflight_cadena_ilegible_se_reporta_sin_romper(proto_dir: Path) -> None:
    # Un fichero guardado en cp1252 con acentos no es UTF-8: el pipeline lo leería
    # con `read_text(encoding="utf-8")` y se caería (auditoría 2026-09-03, M6; D10).
    # El preflight existe para reportarlo, no para romperse con él.
    (proto_dir / "search_strings" / "openalex.txt").write_bytes("búsqueda".encode("cp1252"))
    report = _run(_proto(databases=["OpenAlex"]), proto_dir)  # no debe lanzar
    errores = _messages(report.errors)
    assert "search_strings/openalex.txt" in errores
    assert "no se puede leer como UTF-8" in errores
    assert "UnicodeDecodeError" in errores
    assert "guárdalo en UTF-8" in errores
    assert report.errors[0].where == "databases.OpenAlex"
    # El caso ya es un error: no emite además el aviso de cadena vacía.
    assert "sin cadena" not in _messages(report.warnings)


def test_preflight_cadena_que_es_un_directorio_se_reporta(proto_dir: Path) -> None:
    # `exists()` es verdadero para un directorio; leerlo lanza OSError (IsADirectoryError
    # en POSIX, PermissionError en Windows), no UnicodeDecodeError.
    (proto_dir / "search_strings" / "openalex.txt").unlink()
    (proto_dir / "search_strings" / "openalex.txt").mkdir()
    report = _run(_proto(databases=["OpenAlex"]), proto_dir)
    assert "search_strings/openalex.txt no se puede leer" in _messages(report.errors)
    assert "sin cadena" not in _messages(report.warnings)


def test_preflight_cadena_ilegible_de_base_manual_tambien_es_error(proto_dir: Path) -> None:
    # `search_stage._query_for` lee `search_strings/<base>.txt` también de las bases
    # `manual_only` y la instantánea lee todos los `*.txt`: un `scopus.txt` en cp1252 tumba
    # la corrida aunque Scopus sea manual. El preflight lo reporta igual que para una base
    # con backend.
    (proto_dir / "search_strings" / "scopus.txt").write_bytes("búsqueda".encode("cp1252"))
    report = _run(_proto(databases=["Scopus"]), proto_dir)  # no debe lanzar
    errores = _messages(report.errors)
    assert "search_strings/scopus.txt no se puede leer como UTF-8" in errores
    assert "guárdalo en UTF-8" in errores
    assert [i.where for i in report.errors] == ["databases.Scopus"]


def test_preflight_base_manual_sin_cadena_no_avisa_de_cadena(proto_dir: Path) -> None:
    # Los avisos de "sin cadena" / "cadena vacía" siguen siendo solo para bases con
    # backend: una base manual no usa `search_strings/` (su búsqueda va por imported/).
    (proto_dir / "search_strings" / "scopus.txt").write_text("  \n", "utf-8")
    avisos = _messages(_run(_proto(databases=["Scopus"]), proto_dir).warnings)
    assert "sin cadena" not in avisos
    (proto_dir / "search_strings" / "scopus.txt").unlink()
    avisos = _messages(_run(_proto(databases=["Scopus"]), proto_dir).warnings)
    assert "sin cadena" not in avisos


def test_preflight_imported_solo_cuenta_ficheros(proto_dir: Path) -> None:
    # Un directorio llamado `x.ris` no es una importación: `import_directory` fallaría.
    (proto_dir / "imported" / "x.ris").mkdir(parents=True)
    avisos = _messages(_run(_proto(databases=["OpenAlex", "Scopus"]), proto_dir).warnings)
    assert "no hay ficheros .ris/.bib en imported/" in avisos
    # Con un fichero real junto al directorio, el aviso desaparece.
    (proto_dir / "imported" / "scopus.ris").write_text("TY  - JOUR\nER  -\n", "utf-8")
    avisos = _messages(_run(_proto(databases=["OpenAlex", "Scopus"]), proto_dir).warnings)
    assert "imported/" not in avisos


def test_preflight_databases_vacio_sin_httpx_es_error(proto_dir: Path) -> None:
    # `databases: []` busca en OpenAlex (pipeline: `protocol.databases or ["openalex"]`),
    # que es un backend con httpx: error de httpx además del aviso de lista vacía.
    report = _run(_proto(databases=[]), proto_dir, find_spec=_sin_httpx)
    errores = _messages(report.errors)
    assert "uv sync --extra search" in errores
    assert "OpenAlex" in errores
    assert "`databases` está vacío" in _messages(report.warnings)


def test_preflight_base_desconocida_aconseja_corregir_o_importar(proto_dir: Path) -> None:
    # Quitarla de `databases` la borraría del informe PRISMA-S, y declararla con el nombre
    # de otra base manual la etiquetaría mal ahí: el consejo es corregir la errata (con
    # las claves válidas a la vista) o, si es una base real sin API, importar por RIS/BibTeX
    # y pedir su clave en MANUAL_ONLY para declararla con su propio nombre.
    report = _run(_proto(databases=["OpenAlex", "Scopuss"]), proto_dir)
    mensaje = next(i.message for i in report.errors if "Scopuss" in i.message)
    assert "claves válidas" in mensaje
    assert "openalex" in mensaje and "scopus" in mensaje and "cinahl" in mensaje
    assert "RIS/BibTeX" in mensaje and "imported/" in mensaje
    assert "MANUAL_ONLY" in mensaje
    assert "con el nombre de una base manual" not in mensaje
    assert "quitarla de `databases`" in mensaje  # el aviso de no borrarla se conserva
    assert "quítala" not in mensaje
