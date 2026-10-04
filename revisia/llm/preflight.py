"""Preflight sin red: lo que haría fallar una corrida, detectado antes de empezar.

Hasta la Ola 1, los proveedores se construían al entrar en cada etapa: una API
key ausente para el cribado a texto completo se descubría después de gastar el
cribado de título/abstract, y ``revisia validate`` devolvía 0 con "(sin
proveedor)" (auditoría 2026-09-03, M6). Este módulo revisa, sin tocar la red ni
importar ningún SDK, todo lo que el pipeline va a necesitar: proveedor conocido,
SDK instalado, key en el entorno, binario ``claude``, ``effort`` solo en
``claude_code``, etapas sin proveedor, bases desconocidas, modelos retirados y
``httpx`` (D10).

``env``, ``find_spec`` y ``which`` son inyectables: los tests no dependen de lo
que tenga instalado el venv. ``context`` decide tres cosas: el callback de
``agent`` solo existe en tiempo de corrida (``run``/``resume``: error si falta;
``validate``: aviso); el aviso de ``mailto`` solo tiene sentido en ``run``; en
``resume`` la búsqueda está congelada y se saltan bases y búsqueda.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from revisia.llm.deprecations import retirement_for
from revisia.llm.providers.agent import get_agent_callback
from revisia.llm.registry import _EFFORT_PROVIDERS, available_providers

if TYPE_CHECKING:
    from revisia.config import ReviewProtocol
    from revisia.llm.registry import ProviderConfig

PreflightContext = Literal["validate", "run", "resume"]
FindSpec = Callable[[str], object | None]
Which = Callable[[str], str | None]

# Puntos de inyección por defecto. Los tests de este módulo pasan `env`,
# `find_spec` y `which` explícitos; los del CLI sustituyen estos con monkeypatch.
_default_find_spec: FindSpec = importlib.util.find_spec
_default_which: Which = shutil.which


@dataclass(frozen=True, slots=True)
class Requirement:
    """Lo que necesita un proveedor para funcionar en esta máquina.

    Attributes:
        sdk_module: módulo importable del SDK (``None`` si no usa ninguno).
        extra: extra de ``pyproject.toml`` que lo instala.
        env_var: variable de entorno con la API key (``None`` si no se exige).
        binary: ejecutable que debe estar en el ``PATH``.
        runtime_callback: necesita un callback registrado en tiempo de corrida.
    """

    sdk_module: str | None
    extra: str | None
    env_var: str | None
    binary: str | None
    runtime_callback: bool = False


# Verificado contra `revisia/llm/providers/*.py` y los extras de pyproject.toml.
# Dos tests impiden la deriva: claves == available_providers() y env_var == la
# variable que lee cada clase.
PROVIDER_REQUIREMENTS: dict[str, Requirement] = {
    "gemini": Requirement("google.genai", "gemini", "GEMINI_API_KEY", None),
    "openai": Requirement("openai", "openai", "OPENAI_API_KEY", None),
    "anthropic": Requirement("anthropic", "anthropic", "ANTHROPIC_API_KEY", None),
    # Endpoint local (Ollama/vLLM/LM Studio): la key es opcional.
    "local_openai": Requirement("openai", "local", None, None),
    "zai": Requirement("openai", "zai", "ZAI_API_KEY", None),
    "openrouter": Requirement("openai", "openrouter", "OPENROUTER_API_KEY", None),
    "claude_code": Requirement(None, None, None, "claude"),
    "agent": Requirement(None, None, None, None, runtime_callback=True),
    "fake": Requirement(None, None, None, None),
}


@dataclass(frozen=True, slots=True)
class PreflightIssue:
    """Un problema detectado: ``where`` dice en qué parte del protocolo."""

    level: Literal["error", "warning"]
    where: str
    message: str


@dataclass(frozen=True, slots=True)
class PreflightReport:
    """Resultado del preflight. ``ok`` es ``True`` si no hay errores."""

    issues: tuple[PreflightIssue, ...]

    @property
    def errors(self) -> tuple[PreflightIssue, ...]:
        return tuple(i for i in self.issues if i.level == "error")

    @property
    def warnings(self) -> tuple[PreflightIssue, ...]:
        return tuple(i for i in self.issues if i.level == "warning")

    @property
    def ok(self) -> bool:
        return not self.errors


class PreflightError(ValueError):
    """El preflight encontró errores: la corrida no debe arrancar (rc 2 en el CLI)."""

    def __init__(self, report: PreflightReport) -> None:
        self.report = report
        detalle = "; ".join(f"[{i.where}] {i.message}" for i in report.errors)
        super().__init__(f"preflight con {len(report.errors)} error(es): {detalle}")


def _error(where: str, message: str) -> PreflightIssue:
    return PreflightIssue("error", where, message)


def _warning(where: str, message: str) -> PreflightIssue:
    return PreflightIssue("warning", where, message)


def _importable(module: str, find_spec: FindSpec) -> bool:
    """``find_spec`` envuelto: ``find_spec("google.genai")`` LANZA si falta ``google``."""
    try:
        return find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def _resolve(protocol: ReviewProtocol, stage: str) -> ProviderConfig | None:
    """Proveedor de una etapa, o ``None`` si no tiene ni hay ``default``."""
    try:
        return protocol.provider_for(stage)
    except KeyError:
        return None


def stages_in_use(protocol: ReviewProtocol) -> list[tuple[str, ProviderConfig]]:
    """Proveedores que el pipeline usará de verdad, con la etapa que los usa.

    Miembros de T/A (``screeners_for``), FT, extracción, el primer miembro de
    ``ensemble_llm["extraccion"]`` (2.º extractor), RoB y síntesis (que también
    hace de juez con ``grounding: agent``). Una etapa sin proveedor ni
    ``default`` no aparece: la señala :func:`preflight` como error.
    """
    try:
        members = protocol.screeners_for("screening_ta")
    except KeyError:
        members = []
    used = [
        (f"screening_ta[{i}]" if len(members) > 1 else "screening_ta", cfg)
        for i, cfg in enumerate(members)
    ]
    candidates: list[tuple[str, ProviderConfig | None]] = [
        ("screening_ft", _resolve(protocol, "screening_ft")),
        ("extraccion", _resolve(protocol, "extraccion")),
        ("extraccion_2", next(iter(protocol.ensemble_llm.get("extraccion", [])), None)),
        ("rob", _resolve(protocol, "rob")),
        (
            "sintesis (y juez de grounding)" if protocol.grounding == "agent" else "sintesis",
            _resolve(protocol, "sintesis"),
        ),
    ]
    used += [(where, cfg) for where, cfg in candidates if cfg is not None]
    return used


def _stage_issues(protocol: ReviewProtocol) -> list[PreflightIssue]:
    """Etapas con LLM sin proveedor ni ``default``, y 2.º extractor ambiguo."""
    issues: list[PreflightIssue] = []
    for stage in ("screening_ta", "screening_ft", "extraccion", "rob", "sintesis"):
        try:
            if stage == "screening_ta":
                protocol.screeners_for(stage)
            else:
                protocol.provider_for(stage)
        except KeyError:
            issues.append(
                _error(
                    stage,
                    f"la etapa {stage!r} no tiene proveedor LLM ni hay un 'default' en el "
                    f"bloque llm de protocol.yml: añade llm.{stage} o llm.default.",
                )
            )
    extractores = protocol.ensemble_llm.get("extraccion", [])
    if len(extractores) > 1:
        issues.append(
            _warning(
                "extraccion_2",
                f"ensemble_llm.extraccion declara {len(extractores)} modelos, pero solo se "
                "usa el primero como 2.º extractor.",
            )
        )
    return issues


def check_provider(
    cfg: ProviderConfig,
    *,
    where: str,
    context: PreflightContext,
    env: Mapping[str, str],
    find_spec: FindSpec,
    which: Which,
) -> list[PreflightIssue]:
    """Comprueba que el proveedor de ``cfg`` puede funcionar en esta máquina."""
    req = PROVIDER_REQUIREMENTS.get(cfg.provider)
    if req is None:
        return [
            _error(
                where,
                f"proveedor desconocido {cfg.provider!r}. "
                f"Disponibles: {', '.join(available_providers())}.",
            )
        ]
    issues: list[PreflightIssue] = []
    if cfg.effort is not None and cfg.provider not in _EFFORT_PROVIDERS:
        issues.append(
            _error(
                where,
                f"effort={cfg.effort!r} no aplica al proveedor {cfg.provider!r}; solo lo "
                f"aceptan: {', '.join(sorted(_EFFORT_PROVIDERS))}.",
            )
        )
    if req.sdk_module is not None and not _importable(req.sdk_module, find_spec):
        issues.append(
            _error(
                where,
                f"el proveedor {cfg.provider!r} necesita el paquete {req.sdk_module!r}, que "
                f"no está instalado: `uv sync --extra {req.extra}`.",
            )
        )
    if req.env_var is not None and not env.get(req.env_var):
        issues.append(
            _error(
                where,
                f"falta la variable de entorno {req.env_var} (API key de {cfg.provider!r}): "
                "ponla en .env (ver .env.example) o en el entorno.",
            )
        )
    if req.binary is not None and which(req.binary) is None:
        issues.append(
            _error(
                where,
                f"no se encontró el ejecutable {req.binary!r} de Claude Code en el PATH: "
                "instálalo e inicia sesión antes de correr.",
            )
        )
    if req.runtime_callback and get_agent_callback() is None:
        if context == "validate":
            issues.append(
                _warning(
                    where,
                    "el proveedor 'agent' solo funciona con un callback registrado en "
                    "tiempo de corrida (revisia conducido desde un agente); `revisia run` "
                    "desde la terminal fallará.",
                )
            )
        else:
            issues.append(
                _error(
                    where,
                    "el proveedor 'agent' no tiene callback registrado "
                    "(set_agent_callback/use_agent_callback): en una corrida desatendida "
                    "no hay agente a quien preguntar; elige otro proveedor.",
                )
            )
    return issues


def _configured_models(protocol: ReviewProtocol) -> list[str]:
    """Ids de modelo de todas las etapas y miembros de ensemble del protocolo."""
    models = {cfg.model for cfg in protocol.llm.values()}
    models |= {cfg.model for members in protocol.ensemble_llm.values() for cfg in members}
    return sorted(models)


def check_retired(protocol: ReviewProtocol, today: date) -> list[PreflightIssue]:
    """Modelos retirados por su proveedor (auditoría 2026-09-03, C4).

    Absorbe ``cli._retired_model_problems``: un modelo ya apagado es un error;
    uno con retiro anunciado, un aviso.
    """
    issues: list[PreflightIssue] = []
    for model in _configured_models(protocol):
        retirement = retirement_for(model)
        if retirement is None:
            continue
        fecha = retirement.shutdown.isoformat()
        if retirement.is_past(today):
            issues.append(
                _error(
                    "llm",
                    f"el modelo {model!r} fue retirado por su proveedor el {fecha}; "
                    "las llamadas fallarán. Cámbialo en protocol.yml.",
                )
            )
        else:
            issues.append(
                _warning("llm", f"el modelo {model!r} se retira el {fecha}; planifica el cambio.")
            )
    return issues


def _merge(issues: list[PreflightIssue]) -> tuple[PreflightIssue, ...]:
    """Une los problemas idénticos de varias etapas en uno (``where`` combinado).

    Con el mismo proveedor en cinco etapas, "falta GEMINI_API_KEY" sale una vez.
    """
    merged: dict[tuple[Literal["error", "warning"], str], list[str]] = {}
    for issue in issues:
        wheres = merged.setdefault((issue.level, issue.message), [])
        if issue.where not in wheres:
            wheres.append(issue.where)
    return tuple(
        PreflightIssue(level, ", ".join(wheres), message)
        for (level, message), wheres in merged.items()
    )


def preflight(
    protocol: ReviewProtocol,
    protocol_dir: str | Path,
    *,
    context: PreflightContext,
    mailto: str | None = None,
    env: Mapping[str, str] | None = None,
    find_spec: FindSpec | None = None,
    which: Which | None = None,
    today: date | None = None,
) -> PreflightReport:
    """Revisa, sin red, todo lo que la corrida va a necesitar (M6, D10).

    Args:
        context: ``"validate"``, ``"run"`` o ``"resume"`` (ver docstring del módulo).
        mailto: correo de ``--mailto``; sin él, ``run`` avisa.
        env: entorno a revisar (``os.environ`` por defecto).
        find_spec: como ``importlib.util.find_spec`` (puede lanzar).
        which: como ``shutil.which``.
        today: fecha para los modelos retirados (hoy por defecto).
    """
    env = os.environ if env is None else env
    find_spec = _default_find_spec if find_spec is None else find_spec
    which = _default_which if which is None else which
    today = date.today() if today is None else today

    issues = _stage_issues(protocol)
    for where, cfg in stages_in_use(protocol):
        issues += check_provider(
            cfg, where=where, context=context, env=env, find_spec=find_spec, which=which
        )
    issues += check_retired(protocol, today)
    return PreflightReport(_merge(issues))
