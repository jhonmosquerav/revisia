"""Dobles de prueba compartidos por las pistas de la Ola 1 (spec 2026-10-04 §4.5).

``FakeProvider`` vota siempre ``include`` (el primer valor del ``Literal``,
``fake.py:30``): con él no hay exclusiones, ni gold de dos clases, ni
``unclear`` (hallazgo 5 de la exploración de la Ola 1). ``ScriptedProvider``
etiqueta según palabras clave del prompt, puede simular un 429 en la llamada
``k`` y cuenta las llamadas, para que los tests de reanudación (A9) puedan
afirmar que nada se llama dos veces.

Los ``fetch_fn`` de prueba sustituyen la recuperación de texto completo, que
en la Ola 1 sigue PRISMA estricto (D2): sin ellos, ningún registro de prueba
tiene texto en abierto y nada llega a extracción.

Uso desde un test (``tests/`` está en ``sys.path`` porque no es un paquete)::

    from fakes import ScriptedProvider, fetch_disponible

    proveedor = ScriptedProvider()
    monkeypatch.setattr(pipeline, "build_provider", lambda cfg: proveedor)
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import TypeVar, get_args

from pydantic import BaseModel

from revisia.agents.fulltext import FullText
from revisia.llm.base import LLMRequest, LLMResponse
from revisia.llm.providers.fake import _fabricate_model
from revisia.provenance.runmeta import RunMeta, sha256_text
from revisia.schemas.records import SearchRecord
from revisia.schemas.screening import ScreeningLabel

SchemaT = TypeVar("SchemaT", bound=BaseModel)

# Palabra clave (sin distinguir mayúsculas) → etiqueta. Gana la primera que
# aparezca en el prompt, en este orden; sin coincidencia, ``include``.
PALABRAS_POR_DEFECTO: dict[str, ScreeningLabel] = {
    "irrelevante": "exclude",
    "dudoso": "unclear",
}

_ETIQUETAS = frozenset({"include", "exclude", "unclear"})


class ScriptedProvider:
    """Proveedor con guion: etiqueta por palabra clave, cuenta llamadas y falla a pedido.

    Conserva ``provider="fake"`` y ``deterministic=True`` en cada ``RunMeta``,
    como ``FakeProvider``: el auditor exime de sus heurísticas temporales solo
    a ese proveedor (spec §9.3, ``timing``).

    Attributes:
        model: modelo que declara en ``RunMeta.model``.
        fail_at: número de llamada (1, 2, …) que lanza
            ``RuntimeError("429 Too Many Requests")`` en vez de responder; las
            demás responden con normalidad. ``None`` = nunca falla; un valor
            menor que 1 es un error (``ValueError``).
        calls: llamadas recibidas (``complete`` + ``structured``), incluida la
            que falla.
        prompts: prompt de cada llamada, en orden (para afirmar qué se cribó).
        sintesis: texto que devuelve ``complete`` (la síntesis narrativa); por
            defecto, uno sin citas. Con citas ``[id]`` el verificador tiene algo
            que comprobar (y con un id que no está en el corpus, marca).
    """

    name = "fake"

    def __init__(
        self,
        model: str = "fake-guion",
        *,
        fail_at: int | None = None,
        palabras: Mapping[str, ScreeningLabel] | None = None,
        criterio_exclusion: str = "fuera de alcance",
        sintesis: str | None = None,
    ) -> None:
        # Las llamadas se cuentan desde 1: con `fail_at=0` (o negativo) el 429 nunca
        # se dispararía y el test pasaría sin haber probado la reanudación.
        if fail_at is not None and fail_at < 1:
            raise ValueError(f"fail_at cuenta llamadas desde 1; recibido {fail_at}")
        self.model = model
        self.sintesis = sintesis
        self.fail_at = fail_at
        self.palabras: dict[str, ScreeningLabel] = dict(
            PALABRAS_POR_DEFECTO if palabras is None else palabras
        )
        self.criterio_exclusion = criterio_exclusion
        self.calls = 0
        self.prompts: list[str] = []

    def label_for(self, prompt: str) -> ScreeningLabel:
        """Etiqueta que el guion asigna a ``prompt``."""
        texto = prompt.lower()
        for palabra, etiqueta in self.palabras.items():
            if palabra.lower() in texto:
                return etiqueta
        return "include"

    def _llamar(self, req: LLMRequest) -> None:
        self.calls += 1
        self.prompts.append(req.prompt)
        if self.fail_at is not None and self.calls == self.fail_at:
            raise RuntimeError("429 Too Many Requests")

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
        self._llamar(req)
        # Por defecto sin tokens "[...]": el verificador no debe confundirlos con citas.
        text = self.sintesis or "Síntesis de prueba (proveedor con guion · sin contenido real)."
        return LLMResponse(text=text, meta=self._meta(req, text))

    def structured(self, req: LLMRequest, schema: type[SchemaT]) -> tuple[SchemaT, RunMeta]:
        self._llamar(req)
        data = _fabricate_model(schema).model_dump()
        fields = schema.model_fields
        if "label" in fields and set(get_args(fields["label"].annotation)) >= _ETIQUETAS:
            label = self.label_for(req.prompt)
            data["label"] = label
            if "confidence" in fields:
                data["confidence"] = 0.9
            if "rationale" in fields:
                data["rationale"] = f"guion: {label}"
            if "criteria_violated" in fields:
                data["criteria_violated"] = [self.criterio_exclusion] if label == "exclude" else []
        obj = schema.model_validate(data)
        return obj, self._meta(req, obj.model_dump_json())


def fetch_disponible(record: SearchRecord) -> FullText:
    """``fetch_fn`` de prueba: todo registro tiene texto completo en abierto."""
    text = f"Texto completo de prueba de «{record.title}». {record.abstract or ''}".strip()
    return FullText(
        text=text,
        available=True,
        source_url=f"https://example.org/texto/{sha256_text(record.record_id)[:16]}",
    )


def fetch_no_disponible(ids: Iterable[str]) -> Callable[[SearchRecord], FullText]:
    """``fetch_fn`` de prueba: los ``ids`` dados no se recuperan; el resto sí.

    El ``FullText`` de un no recuperado lleva el abstract en ``text`` y
    ``available=False``, como el fallback real de
    :func:`revisia.agents.fulltext.fetch_fulltext`.
    """
    if isinstance(ids, str):
        # `frozenset("10.1/b")` troceaba el id en caracteres y el registro salía disponible.
        raise TypeError(f"ids debe ser una colección de ids (p. ej. ['{ids}']), no un str")
    sin_texto = frozenset(ids)

    def _fetch(record: SearchRecord) -> FullText:
        if record.record_id in sin_texto:
            return FullText(text=record.abstract or "", available=False)
        return fetch_disponible(record)

    return _fetch
