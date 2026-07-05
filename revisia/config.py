"""Puente motor↔config · carga y valida ``protocol.yml`` de una revisión.

El motor (``revisia``) no contiene nada de una revisión concreta. Toda
revisión vive en ``protocols/<slug>/`` y se describe con ``protocol.yml`` (más
``inclusion_exclusion.yml``, ``extraction_form.yml`` y ``search_strings/``).
Este módulo es la frontera: convierte esa config en un objeto validado que el
orquestador y los agentes consumen.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from revisia.llm.registry import ProviderConfig
from revisia.schemas.question import ResearchQuestion
from revisia.schemas.rob import RoBTool

# Orden canónico de etapas del pipeline (espeja el documento metodológico).
STAGES: tuple[str, ...] = (
    "protocolo",
    "busqueda",
    "dedup",
    "screening_ta",
    "screening_ft",
    "extraccion",
    "rob",
    "sintesis",
    "reporte",
)

# Autonomía por defecto si el protocolo no la especifica. Regla no negociable:
# screening/extracción/rob nunca superan A1; el resto de razonamiento A1; las
# etapas deterministas A2.
DEFAULT_AUTONOMY: dict[str, str] = {
    "protocolo": "A0",
    "busqueda": "A2",
    "dedup": "A2",
    "screening_ta": "A1",
    "screening_ft": "A0",
    "extraccion": "A0",
    "rob": "A0",
    "sintesis": "A1",
    "reporte": "A1",
}


class ReviewProtocol(BaseModel):
    """Protocolo de una revisión sistemática concreta (config validada).

    Attributes:
        slug: identificador en kebab-case (== nombre de la carpeta).
        title: título legible de la revisión.
        question: pregunta de investigación estructurada.
        databases: bases de datos/fuentes a consultar.
        rob_tool: herramienta de riesgo de sesgo acorde al diseño esperado.
        prisma_extension: extensión PRISMA aplicable (ej. ``PRISMA-2020``).
        llm: config de proveedor por etapa; la clave ``default`` es el fallback.
        autonomy: nivel de autonomía por etapa (``A0``..``A3``).
        thresholds: umbrales (ej. ``kappa_min``, ``recall_target``).
        registration: registro del protocolo (ej. ``{"prospero": "CRD..."}``).
        ensemble: nombres de etapas que corren en modo ensemble multi-modelo.
        search_window: ventana temporal de la búsqueda (``{from, to, executed}``),
            fechas de inicio/cierre/ejecución exigidas por PRISMA-S (§3).
    """

    slug: str
    title: str
    question: ResearchQuestion
    databases: list[str] = Field(default_factory=list)
    rob_tool: RoBTool = "RoB2"
    prisma_extension: str = "PRISMA-2020"
    llm: dict[str, ProviderConfig] = Field(default_factory=dict)
    ensemble_llm: dict[str, list[ProviderConfig]] = Field(default_factory=dict)
    autonomy: dict[str, str] = Field(default_factory=dict)
    thresholds: dict[str, float] = Field(default_factory=dict)
    registration: dict[str, str] = Field(default_factory=dict)
    ensemble: list[str] = Field(default_factory=list)
    search_window: dict[str, str] = Field(default_factory=dict)
    # Modo de grounding del verificador: "embedder" (coseno, léxico/portátil),
    # "agent" (un modelo juzga; cruza idiomas, sin vectores) o "existence" (solo
    # comprueba que el id citado exista en el corpus). Default: embedder.
    grounding: str = "embedder"

    def autonomy_for(self, stage: str) -> str:
        """Autonomía efectiva de una etapa (config > default)."""
        return self.autonomy.get(stage, DEFAULT_AUTONOMY.get(stage, "A0"))

    def provider_for(self, stage: str) -> ProviderConfig:
        """Config de proveedor de una etapa (cae a ``default`` si no hay)."""
        if stage in self.llm:
            return self.llm[stage]
        if "default" in self.llm:
            return self.llm["default"]
        raise KeyError(
            f"No hay proveedor LLM para la etapa {stage!r} ni un 'default' en protocol.yml."
        )

    def screeners_for(self, stage: str) -> list[ProviderConfig]:
        """Proveedores que cribán una etapa.

        Si la etapa está marcada como ``ensemble`` y tiene varios modelos en
        ``ensemble_llm``, devuelve todos (voto multi-modelo sesgado a recall);
        en caso contrario, un único proveedor (el de ``provider_for``).
        """
        if stage in self.ensemble and self.ensemble_llm.get(stage):
            return self.ensemble_llm[stage]
        return [self.provider_for(stage)]


def load_protocol(protocol_dir: str | Path) -> ReviewProtocol:
    """Carga y valida ``protocol.yml`` desde una carpeta de protocolo.

    Args:
        protocol_dir: carpeta que contiene ``protocol.yml``.

    Raises:
        FileNotFoundError: si no existe ``protocol.yml``.
    """
    base = Path(protocol_dir)
    protocol_file = base / "protocol.yml"
    if not protocol_file.exists():
        raise FileNotFoundError(f"No se encontró {protocol_file}.")
    raw = yaml.safe_load(protocol_file.read_text(encoding="utf-8")) or {}
    raw.setdefault("slug", base.name)
    return ReviewProtocol.model_validate(raw)
