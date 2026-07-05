"""Proveedor local OpenAI-compatible (Ollama / vLLM / LM Studio).

Cubre el caso "100% local y abierto": cualquier endpoint que exponga la API de
OpenAI (``base_url`` vía ``LOCAL_OPENAI_BASE_URL``). Es la vía para que un
investigador reproduzca la revisión sin enviar datos a terceros (relevante para
PRISMA-trAIce · gobernanza de datos sensibles).

Reutiliza ``_OpenAIBase`` para ``complete``, pero sobreescribe ``structured``:
muchos servidores locales soportan ``response_format=json_object`` pero no el
``json_schema`` estricto de OpenAI, así que se inyecta el schema en el prompt y
se valida la respuesta con Pydantic.
"""

from __future__ import annotations

import json
import os
from typing import Any, TypeVar

from pydantic import BaseModel

from prisma_loop.llm.base import LLMRequest
from prisma_loop.llm.providers.openai_api import _OpenAIBase
from prisma_loop.provenance.runmeta import RunMeta

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class LocalOpenAIProvider(_OpenAIBase):
    """Proveedor LLM contra un endpoint local OpenAI-compatible."""

    name = "local_openai"
    env_key = "LOCAL_OPENAI_API_KEY"

    def __init__(self, model: str) -> None:
        super().__init__(model)
        self.base_url = os.environ.get("LOCAL_OPENAI_BASE_URL") or "http://localhost:11434/v1"

    def structured(self, req: LLMRequest, schema: type[SchemaT]) -> tuple[SchemaT, RunMeta]:
        client = self._client()
        schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        augmented = (
            f"{req.prompt}\n\nResponde ÚNICAMENTE con un JSON válido que cumpla "
            f"este JSON Schema (sin texto adicional):\n{schema_json}"
        )
        messages = self._messages(LLMRequest(prompt=augmented, system=req.system))
        resp: Any = client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=req.temperature,
            top_p=req.top_p,
            seed=req.seed,
            max_tokens=req.max_tokens,
            response_format={"type": "json_object"},
        )
        text = resp.choices[0].message.content or "{}"
        obj = schema.model_validate_json(text)
        return obj, self._meta(req, text, resp)
