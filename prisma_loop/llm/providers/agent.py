"""Proveedor ``agent`` · delega el razonamiento en el agente de la sesión.

Pensado para cuando prisma-loop se **conduce en proceso** desde la sesión de un
agente (p. ej. Claude Code) en vez de correr como CLI. El agente orquestador
inyecta un *callback* que produce la salida de cada etapa, de modo que el
razonamiento usa la sesión ya autenticada del agente: sin API key y sin
``claude -p`` headless (que no puede heredar la auth del host —ver
:mod:`prisma_loop.llm.providers.claude_code`—).

A diferencia de ``claude_code``, este proveedor **no lanza ningún proceso**: el
agente *es* el modelo. El callback se registra antes de correr el pipeline:

    from prisma_loop.llm.providers.agent import use_agent_callback

    def reason(req, schema):
        # el agente lee req.prompt y devuelve un dict/objeto que cumple `schema`
        # (o un str si schema es None, para texto libre).
        ...

    with use_agent_callback(reason):
        run_pipeline(...)   # las etapas con provider: agent usan `reason`

Si se configura ``provider: agent`` pero no hay callback registrado, falla con un
error accionable: en una corrida CLI desatendida no hay agente a quien preguntar.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from prisma_loop.llm.base import LLMRequest, LLMResponse
from prisma_loop.provenance.runmeta import RunMeta, sha256_text

SchemaT = TypeVar("SchemaT", bound=BaseModel)

# El callback recibe la petición y el schema esperado (``None`` para texto libre)
# y devuelve un objeto/diccionario que cumple el schema, o un str si es libre.
AgentCallback = Callable[[LLMRequest, "type[BaseModel] | None"], "BaseModel | dict | str"]

# Registro de proceso del callback activo (lo fija el agente orquestador).
_CALLBACK: AgentCallback | None = None


def set_agent_callback(callback: AgentCallback | None) -> None:
    """Registra (o limpia con ``None``) el callback que el proveedor usará."""
    global _CALLBACK
    _CALLBACK = callback


def get_agent_callback() -> AgentCallback | None:
    """Devuelve el callback activo, o ``None`` si no se ha registrado."""
    return _CALLBACK


@contextmanager
def use_agent_callback(callback: AgentCallback) -> Iterator[None]:
    """Context manager que activa ``callback`` solo dentro del bloque."""
    previous = _CALLBACK
    set_agent_callback(callback)
    try:
        yield
    finally:
        set_agent_callback(previous)


def _extract_json(text: str) -> str:
    """Aísla el objeto JSON de un str que puede traer texto/fences."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1] if "\n" in cleaned else cleaned
        if cleaned.endswith("```"):
            cleaned = cleaned[: -len("```")]
        cleaned = cleaned.strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        return cleaned[start : end + 1]
    return cleaned


class AgentProvider:
    """Proveedor LLM respaldado por el agente de la sesión (vía callback)."""

    name = "agent"

    def __init__(self, model: str = "session-agent") -> None:
        self.model = model

    def _require_callback(self) -> AgentCallback:
        cb = get_agent_callback()
        if cb is None:
            raise RuntimeError(
                "El proveedor 'agent' requiere un callback registrado con "
                "set_agent_callback()/use_agent_callback() antes de correr el "
                "pipeline. Úsalo solo cuando conduces prisma-loop en proceso "
                "desde un agente; para una corrida CLI desatendida elige otro "
                "proveedor (gemini/openai/anthropic/claude_code/fake)."
            )
        return cb

    def _meta(self, req: LLMRequest, payload: str) -> RunMeta:
        return RunMeta(
            provider=self.name,
            model=self.model,
            seed=req.seed,
            temperature=req.temperature,
            top_p=req.top_p,
            prompt_sha256=sha256_text(f"{req.system or ''}\n{req.prompt}"),
            response_sha256=sha256_text(payload),
            deterministic=False,  # el juicio del agente no es estable a nivel token
        )

    def complete(self, req: LLMRequest) -> LLMResponse:
        cb = self._require_callback()
        out = cb(req, None)
        if isinstance(out, BaseModel):
            text = out.model_dump_json()
        elif isinstance(out, dict):
            text = json.dumps(out, ensure_ascii=False)
        else:
            text = str(out)
        return LLMResponse(text=text, meta=self._meta(req, text))

    def structured(self, req: LLMRequest, schema: type[SchemaT]) -> tuple[SchemaT, RunMeta]:
        cb = self._require_callback()
        out = cb(req, schema)
        try:
            if isinstance(out, schema):
                obj: SchemaT = out
            elif isinstance(out, BaseModel):
                obj = schema.model_validate(out.model_dump())
            elif isinstance(out, dict):
                obj = schema.model_validate(out)
            else:
                obj = schema.model_validate_json(_extract_json(str(out)))
        except (ValidationError, ValueError) as exc:
            raise RuntimeError(
                f"El callback del agente no produjo una salida válida para "
                f"{schema.__name__}: {str(exc)[:200]}"
            ) from exc
        return obj, self._meta(req, obj.model_dump_json())
