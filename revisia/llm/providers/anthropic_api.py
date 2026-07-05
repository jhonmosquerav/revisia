"""Proveedor Anthropic (SDK ``anthropic``, API directa).

Importante: este proveedor habla con la **API de Anthropic**, NO con Claude Code.
El driver de Claude Code es un proveedor distinto y opcional
(:mod:`revisia.llm.providers.claude_code`).

Implementa el contrato :class:`revisia.llm.base.LLMProvider`:
- ``complete`` usa la Messages API.
- ``structured`` usa *tool use* forzado: se declara una herramienta cuyo
  ``input_schema`` es el JSON Schema del modelo Pydantic y se obliga al modelo a
  llamarla, de modo que la salida llega ya tipada (patrón nativo de Anthropic
  para structured output). El SDK se importa de forma perezosa: el núcleo no
  exige ``anthropic`` salvo que la config lo pida.

Anthropic no soporta ``seed``; la reproducibilidad queda a nivel de decisión
(ledger), no de token (``deterministic=False``).
"""

from __future__ import annotations

import os
from typing import Any, TypeVar

from pydantic import BaseModel

from revisia.llm.base import LLMRequest, LLMResponse
from revisia.provenance.runmeta import RunMeta, sha256_text

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class AnthropicProvider:
    """Proveedor LLM respaldado por la API directa de Anthropic."""

    name = "anthropic"
    env_key = "ANTHROPIC_API_KEY"

    def __init__(self, model: str) -> None:
        self.model = model

    # ── infraestructura ────────────────────────────────────────────────
    def _client(self) -> Any:
        from anthropic import Anthropic

        api_key = os.environ.get(self.env_key)
        if not api_key:
            raise RuntimeError(f"{self.env_key} no está definida en el entorno.")
        return Anthropic(api_key=api_key)

    def _kwargs(self, req: LLMRequest) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": req.max_tokens,
            "temperature": req.temperature,
            "messages": [{"role": "user", "content": req.prompt}],
        }
        if req.system:
            kwargs["system"] = req.system
        if req.top_p is not None:
            kwargs["top_p"] = req.top_p
        return kwargs

    def _meta(self, req: LLMRequest, text: str, resp: Any) -> RunMeta:
        usage = getattr(resp, "usage", None)
        return RunMeta(
            provider=self.name,
            model=self.model,
            model_version=getattr(resp, "model", None),
            seed=req.seed,
            temperature=req.temperature,
            top_p=req.top_p,
            prompt_sha256=sha256_text(f"{req.system or ''}\n{req.prompt}"),
            response_sha256=sha256_text(text),
            input_tokens=getattr(usage, "input_tokens", None) if usage else None,
            output_tokens=getattr(usage, "output_tokens", None) if usage else None,
            deterministic=False,  # Anthropic no soporta seed
        )

    # ── contrato LLMProvider ───────────────────────────────────────────
    def complete(self, req: LLMRequest) -> LLMResponse:
        client = self._client()
        resp = client.messages.create(**self._kwargs(req))
        text = "".join(
            block.text for block in resp.content if getattr(block, "type", None) == "text"
        )
        return LLMResponse(text=text, meta=self._meta(req, text, resp))

    def structured(self, req: LLMRequest, schema: type[SchemaT]) -> tuple[SchemaT, RunMeta]:
        client = self._client()
        tool_name = schema.__name__
        kwargs = self._kwargs(req)
        kwargs["tools"] = [
            {
                "name": tool_name,
                "description": f"Devuelve un objeto {tool_name} validado.",
                "input_schema": schema.model_json_schema(),
            }
        ]
        kwargs["tool_choice"] = {"type": "tool", "name": tool_name}
        resp = client.messages.create(**kwargs)
        tool_use = next(
            (b for b in resp.content if getattr(b, "type", None) == "tool_use"),
            None,
        )
        if tool_use is None:  # el modelo no llamó a la herramienta
            raise RuntimeError("Anthropic no devolvió salida estructurada (sin tool_use).")
        obj = schema.model_validate(tool_use.input)
        return obj, self._meta(req, obj.model_dump_json(), resp)
