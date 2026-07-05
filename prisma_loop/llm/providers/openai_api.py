"""Proveedor OpenAI (SDK ``openai``) + base compartida para servidores
OpenAI-compatibles.

``_OpenAIBase`` implementa el contrato :class:`prisma_loop.llm.base.LLMProvider`
sobre la API de chat de OpenAI; ``LocalOpenAIProvider`` la reutiliza apuntando a
un endpoint local. El SDK se importa de forma perezosa (solo al llamar al
modelo), así el núcleo no exige ``openai`` salvo que la config lo pida.
"""

from __future__ import annotations

import os
from typing import Any, TypeVar

from pydantic import BaseModel

from prisma_loop.llm.base import LLMRequest, LLMResponse
from prisma_loop.provenance.runmeta import RunMeta, sha256_text

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class _OpenAIBase:
    """Base para proveedores que hablan la API de chat de OpenAI."""

    name = "openai"
    env_key = "OPENAI_API_KEY"

    def __init__(self, model: str) -> None:
        self.model = model
        self.base_url: str | None = None

    # ── infraestructura ────────────────────────────────────────────────
    def _client(self) -> Any:
        from openai import OpenAI

        api_key = os.environ.get(self.env_key)
        if not api_key and self.base_url is None:
            raise RuntimeError(f"{self.env_key} no está definida en el entorno.")
        return OpenAI(api_key=api_key or "not-needed", base_url=self.base_url)

    def _messages(self, req: LLMRequest) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if req.system:
            messages.append({"role": "system", "content": req.system})
        messages.append({"role": "user", "content": req.prompt})
        return messages

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
            input_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
            output_tokens=getattr(usage, "completion_tokens", None) if usage else None,
            deterministic=False,  # seed es best-effort en OpenAI
        )

    # ── contrato LLMProvider ───────────────────────────────────────────
    def complete(self, req: LLMRequest) -> LLMResponse:
        client = self._client()
        resp = client.chat.completions.create(
            model=self.model,
            messages=self._messages(req),
            temperature=req.temperature,
            top_p=req.top_p,
            seed=req.seed,
            max_tokens=req.max_tokens,
        )
        text = resp.choices[0].message.content or ""
        return LLMResponse(text=text, meta=self._meta(req, text, resp))

    def structured(self, req: LLMRequest, schema: type[SchemaT]) -> tuple[SchemaT, RunMeta]:
        client = self._client()
        completion = client.beta.chat.completions.parse(
            model=self.model,
            messages=self._messages(req),
            response_format=schema,
            temperature=req.temperature,
            top_p=req.top_p,
            seed=req.seed,
            max_tokens=req.max_tokens,
        )
        message = completion.choices[0].message
        obj = message.parsed
        if obj is None:  # el modelo rehusó o no devolvió structured output
            raise RuntimeError(f"OpenAI no devolvió salida estructurada: {message.refusal!r}")
        text = message.content or obj.model_dump_json()
        return obj, self._meta(req, text, completion)


class OpenAIProvider(_OpenAIBase):
    """Proveedor LLM respaldado por la API de OpenAI."""

    name = "openai"
    env_key = "OPENAI_API_KEY"
