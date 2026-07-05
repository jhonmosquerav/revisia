"""Proveedor Gemini (SDK ``google-genai``).

Implementa el contrato :class:`revisia.llm.base.LLMProvider` sobre el SDK
oficial de Google. El SDK se importa de forma perezosa para no exigirlo a quien
no use Gemini.

Proveedor por defecto de la plantilla (``gemini-2.0-flash``): tier gratis y sin
fricción para empezar. Cualquier investigador puede elegir otro proveedor en
``protocol.yml`` sin tocar nada del núcleo.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, TypeVar

from pydantic import BaseModel

from revisia.llm.base import LLMRequest, LLMResponse
from revisia.provenance.runmeta import RunMeta, sha256_text

if TYPE_CHECKING:
    from google import genai

SchemaT = TypeVar("SchemaT", bound=BaseModel)

DEFAULT_MODEL = "gemini-2.0-flash"


class GeminiProvider:
    """Proveedor LLM respaldado por Google Gemini."""

    name = "gemini"

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self.model = model

    # ── infraestructura ────────────────────────────────────────────────
    def _client(self) -> genai.Client:
        from google import genai

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY no está definida en el entorno.")
        return genai.Client(api_key=api_key)

    def _config(self, req: LLMRequest, **extra: Any) -> Any:
        from google.genai import types as genai_types

        return genai_types.GenerateContentConfig(
            system_instruction=req.system,
            temperature=req.temperature,
            top_p=req.top_p,
            max_output_tokens=req.max_tokens,
            seed=req.seed,
            **extra,
        )

    def _meta(self, req: LLMRequest, text: str, resp: Any) -> RunMeta:
        usage = getattr(resp, "usage_metadata", None)
        return RunMeta(
            provider=self.name,
            model=self.model,
            model_version=getattr(resp, "model_version", None),
            seed=req.seed,
            temperature=req.temperature,
            top_p=req.top_p,
            prompt_sha256=sha256_text(f"{req.system or ''}\n{req.prompt}"),
            response_sha256=sha256_text(text),
            input_tokens=getattr(usage, "prompt_token_count", None) if usage else None,
            output_tokens=getattr(usage, "candidates_token_count", None) if usage else None,
            deterministic=False,  # Gemini no garantiza determinismo a nivel token
        )

    # ── contrato LLMProvider ───────────────────────────────────────────
    def complete(self, req: LLMRequest) -> LLMResponse:
        client = self._client()
        resp = client.models.generate_content(
            model=self.model, contents=req.prompt, config=self._config(req)
        )
        text = resp.text or ""
        return LLMResponse(text=text, meta=self._meta(req, text, resp))

    def structured(self, req: LLMRequest, schema: type[SchemaT]) -> tuple[SchemaT, RunMeta]:
        client = self._client()
        resp = client.models.generate_content(
            model=self.model,
            contents=req.prompt,
            config=self._config(req, response_mime_type="application/json", response_schema=schema),
        )
        text = resp.text or ""
        # El SDK puede entregar ya el objeto parseado; si no, validamos el texto.
        parsed = getattr(resp, "parsed", None)
        obj = parsed if isinstance(parsed, schema) else schema.model_validate_json(text)
        return obj, self._meta(req, text, resp)
