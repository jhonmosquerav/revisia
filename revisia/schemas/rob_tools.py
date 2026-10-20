"""Especificaciones oficiales de las herramientas de riesgo de sesgo como datos (D5).

La auditoría 2026-09-03 (A12) encontró dominios de RoB inventados: un revisor que conozca la
herramienta los ve a la primera. Desde la Ola 2 cada herramienta vive en un YAML del paquete
(``revisia/rob/tools/<RoBTool>.yml``) con su estructura oficial —ids y nombres de dominios o
ítems, número y orden de las preguntas señalizadoras, escalas y regla de agregación— y este
módulo la valida **al cargar**: un dominio repetido, un ítem crítico inexistente o una escala
vacía es un error del motor y no llega a ninguna corrida (riesgo 5 del spec).

Las preguntas son paráfrasis propias con el id oficial; el texto literal no se transcribe
porque RoB 2 y ROBINS-I se publican bajo CC BY-NC-ND y el paquete es Apache-2.0 (§4.4).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, get_args

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from revisia.provenance.runmeta import sha256_text
from revisia.schemas.rob import RoBTool

TOOLS_DIR: Path = Path(__file__).resolve().parent.parent / "rob" / "tools"
# Las seis herramientas, derivadas del ``Literal`` para que no se desincronicen.
TOOLS: tuple[RoBTool, ...] = get_args(RoBTool)


def _escala_valida(valores: list[str], donde: str) -> None:
    """Una escala de juicio necesita al menos dos valores distintos para discriminar algo."""
    if len(valores) < 2:
        raise ValueError(f"{donde}: la escala necesita al menos 2 valores")
    if len(set(valores)) != len(valores):
        raise ValueError(f"{donde}: la escala tiene valores repetidos")


class SignallingQuestion(BaseModel):
    """Pregunta señalizadora: id oficial y paráfrasis propia (nunca el texto literal, §4.4)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=200)
    answers: list[str] = Field(min_length=2)

    @model_validator(mode="after")
    def _respuestas_distintas(self) -> SignallingQuestion:
        if len(set(self.answers)) != len(self.answers):
            raise ValueError(f"pregunta {self.id}: respuestas repetidas {self.answers}")
        return self


class RoBDomainSpec(BaseModel):
    """Dominio (o ítem, en AMSTAR 2 y NOS) con sus preguntas y, si difiere, su escala."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    signalling_questions: list[SignallingQuestion] = Field(default_factory=list)
    scale: list[str] | None = None

    @model_validator(mode="after")
    def _escala_propia(self) -> RoBDomainSpec:
        if self.scale is not None:
            _escala_valida(self.scale, f"dominio {self.id}")
        return self


class ApplicabilitySpec(BaseModel):
    """Dominio de aplicabilidad (QUADAS-2)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)


class ToolSource(BaseModel):
    """Referencia a la fuente oficial y por qué su texto no se transcribe."""

    model_config = ConfigDict(extra="forbid")

    citation: str = Field(min_length=1)
    url: str = Field(min_length=1)
    version: str = Field(min_length=1)
    license_note: str = Field(min_length=1)


class RoBToolSpec(BaseModel):
    """Especificación de una herramienta de riesgo de sesgo (§4.2 «RoBToolSpec», D5).

    Attributes:
        unit: ``domain`` (juicio por dominio), ``item`` (AMSTAR 2) o ``star`` (NOS).
        judgment_scale: escala por defecto de cada dominio.
        overall_scale: escala del juicio global; ``None`` si la herramienta no lo produce.
        aggregation: regla que lleva de los dominios al global.
        critical_items: ids de dominios críticos (AMSTAR 2).
        applicability: dominios de aplicabilidad (QUADAS-2).
    """

    model_config = ConfigDict(extra="forbid")

    id: RoBTool
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    unit: Literal["domain", "item", "star"]
    judgment_scale: list[str]
    overall_scale: list[str] | None = None
    domains: list[RoBDomainSpec] = Field(min_length=1)
    aggregation: Literal["rob2", "robins_i", "amstar2", "nos_stars", "none"]
    critical_items: list[str] = Field(default_factory=list)
    applicability: list[ApplicabilitySpec] = Field(default_factory=list)
    robvis_template: Literal["rob2", "robins_i", "quadas2", "generic"]
    source: ToolSource

    @model_validator(mode="after")
    def _coherente(self) -> RoBToolSpec:
        """Riesgo 5: una especificación mal transcrita debe fallar al cargar, no en la corrida."""
        _escala_valida(self.judgment_scale, f"{self.id}.judgment_scale")
        if self.overall_scale is not None:
            _escala_valida(self.overall_scale, f"{self.id}.overall_scale")
        ids = [d.id for d in self.domains]
        repetidos = sorted({i for i in ids if ids.count(i) > 1})
        if repetidos:
            raise ValueError(f"{self.id}: ids de dominio repetidos {repetidos}")
        criticos = [c for c in self.critical_items if c not in ids]
        if criticos:
            raise ValueError(f"{self.id}: critical_items sin dominio {criticos}")
        if len(set(self.critical_items)) != len(self.critical_items):
            raise ValueError(f"{self.id}: critical_items repetidos")
        preguntas = [q.id for d in self.domains for q in d.signalling_questions]
        repetidas = sorted({q for q in preguntas if preguntas.count(q) > 1})
        if repetidas:
            raise ValueError(f"{self.id}: ids de pregunta repetidos {repetidas}")
        for posicion, dominio in enumerate(self.domains, 1):
            # El id oficial es «<n.º de dominio>.<n.º de pregunta>»: una pregunta colocada en
            # otro dominio es un error de transcripción (riesgo 5).
            for q in dominio.signalling_questions:
                if q.id.split(".", 1)[0] != str(posicion) or "." not in q.id:
                    raise ValueError(
                        f"{self.id}: la pregunta {q.id} no lleva el prefijo «{posicion}.» "
                        f"de su dominio {dominio.id}"
                    )
        aplic = [a.id for a in self.applicability]
        if len(set(aplic)) != len(aplic):
            raise ValueError(f"{self.id}: ids de aplicabilidad repetidos")
        if self.aggregation == "none" and self.overall_scale is not None:
            raise ValueError(f"{self.id}: aggregation 'none' no admite overall_scale")
        if self.aggregation in {"rob2", "robins_i", "amstar2"} and self.overall_scale is None:
            raise ValueError(f"{self.id}: aggregation '{self.aggregation}' exige overall_scale")
        return self

    @property
    def domain_ids(self) -> tuple[str, ...]:
        """Ids de los dominios o ítems, en el orden oficial."""
        return tuple(d.id for d in self.domains)

    @property
    def n_questions(self) -> int:
        """Número total de preguntas señalizadoras."""
        return sum(len(d.signalling_questions) for d in self.domains)

    def scale_for(self, domain_id: str) -> tuple[str, ...]:
        """Escala válida del dominio (la suya o la de la herramienta); ``KeyError`` si no existe."""
        for dominio in self.domains:
            if dominio.id == domain_id:
                return tuple(dominio.scale if dominio.scale is not None else self.judgment_scale)
        raise KeyError(domain_id)


def tool_spec_path(tool: RoBTool) -> Path:
    """Ruta del YAML de la herramienta: su nombre es el literal de ``RoBTool``."""
    return TOOLS_DIR / f"{tool}.yml"


def load_tool_spec(tool: RoBTool) -> RoBToolSpec:
    """Lee y valida la especificación de ``tool``.

    El YAML es del paquete: si no valida es un error del motor, no del usuario, y el
    ``ValueError`` nombra el fichero para que se corrija ahí.
    """
    path = tool_spec_path(tool)
    try:
        datos = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"especificación de RoB ilegible en {path.name}: {exc}") from exc
    try:
        spec = RoBToolSpec.model_validate(datos)
    except ValidationError as exc:
        raise ValueError(f"especificación de RoB inválida en {path.name}: {exc}") from exc
    if spec.id != tool:
        raise ValueError(f"{path.name} declara id {spec.id!r}, se esperaba {tool!r}")
    return spec


def tool_spec_fingerprint() -> dict[str, str]:
    """Huella ``{"rob/<tool>.yml": sha256}`` de las seis especificaciones, ordenada por clave.

    Misma regla de hash que ``snapshot._text_sha256`` (texto UTF-8 con CRLF→LF): PR-A la
    mezcla en ``environment.prompt_templates``.
    """
    huella = {
        f"rob/{tool}.yml": sha256_text(
            tool_spec_path(tool).read_bytes().decode("utf-8").replace("\r\n", "\n")
        )
        for tool in TOOLS
    }
    return dict(sorted(huella.items()))
