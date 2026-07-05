"""Proveedor ``fake`` · determinista y offline (sin red ni API key).

Sirve para dos cosas: (1) correr el pipeline end-to-end sin credenciales —
útil para tests y para que el investigador vea el sistema funcionar antes de
configurar un proveedor real— y (2) reproducibilidad: su salida es estable
(``deterministic=True``).

Para ``structured`` fabrica una instancia válida del schema pedido rellenando
los campos requeridos según su tipo. NO produce contenido semánticamente
correcto: es un doble de pruebas, no un revisor.
"""

from __future__ import annotations

import enum
import types
from typing import Any, Literal, TypeVar, Union, get_args, get_origin

from pydantic import BaseModel

from revisia.llm.base import LLMRequest, LLMResponse
from revisia.provenance.runmeta import RunMeta, sha256_text

SchemaT = TypeVar("SchemaT", bound=BaseModel)


def _fabricate_value(annotation: Any, name: str) -> Any:
    origin = get_origin(annotation)
    if origin is Literal:
        return get_args(annotation)[0]
    if origin in (Union, types.UnionType):
        non_none = [a for a in get_args(annotation) if a is not type(None)]
        return _fabricate_value(non_none[0], name) if non_none else None
    if origin in (list, set, tuple):
        return []
    if origin is dict:
        return {}
    if isinstance(annotation, type):
        if issubclass(annotation, BaseModel):
            return _fabricate_model(annotation)
        if issubclass(annotation, enum.Enum):
            return next(iter(annotation))
        if annotation is bool:
            return True
        if annotation is float:
            return 0.8 if "conf" in name.lower() else 0.0
        if annotation is int:
            return 1
        if annotation is str:
            return f"fake:{name}"
    return None


def _fabricate_model(schema: type[BaseModel]) -> BaseModel:
    data: dict[str, Any] = {}
    for field_name, field in schema.model_fields.items():
        if field.is_required():
            data[field_name] = _fabricate_value(field.annotation, field_name)
    return schema.model_validate(data)


class FakeProvider:
    """Doble de pruebas que implementa el contrato LLMProvider sin red."""

    name = "fake"

    def __init__(self, model: str = "fake-1") -> None:
        self.model = model

    def _meta(self, req: LLMRequest, text: str) -> RunMeta:
        return RunMeta(
            provider=self.name,
            model=self.model,
            seed=req.seed,
            temperature=req.temperature,
            top_p=req.top_p,
            prompt_sha256=sha256_text(f"{req.system or ''}\n{req.prompt}"),
            response_sha256=sha256_text(text),
            deterministic=True,
        )

    def complete(self, req: LLMRequest) -> LLMResponse:
        # Texto benigno y SIN tokens "[...]": el proveedor fake no debe emitir
        # algo que el verificador confunda con una cita.
        text = (
            "Borrador de síntesis narrativa (proveedor fake · sin contenido real). "
            "Configura un proveedor LLM real en protocol.yml para generar la síntesis."
        )
        return LLMResponse(text=text, meta=self._meta(req, text))

    def structured(self, req: LLMRequest, schema: type[SchemaT]) -> tuple[SchemaT, RunMeta]:
        obj = _fabricate_model(schema)
        return obj, self._meta(req, obj.model_dump_json())  # type: ignore[return-value]
