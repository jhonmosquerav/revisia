"""Panel y resultado de ``revisia benchmark`` (spec 2026-10-18 §4.2; D6, D23).

Solo modelos: la orquestación llega en PR-F. Una corrida de benchmark es una corrida
normal con ``kind: benchmark`` sobre un corpus congelado (D6); el estudio comparativo
vive fuera del motor (D23), que solo ofrece el panel, el gold y las métricas.

Este módulo **no se exporta** desde ``revisia/schemas/__init__.py``: ``revisia.metrics``
importa ``revisia.schemas.screening`` y exportarlo aquí cerraría un ciclo al importar el
paquete.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from revisia.config import rechazar_claves_de_fusion
from revisia.llm.registry import ProviderConfig
from revisia.metrics import ScreeningMetrics
from revisia.provenance.runmeta import utc_now_iso
from revisia.schemas.artifacts import ARTIFACT_SCHEMA_VERSION, Environment

# El nombre de la celda es parte de la carpeta ``runs/<celda>-r<k>/``: solo caracteres
# seguros como nombre de fichero en cualquier sistema.
_CELL_NAME_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,39}$"


class BenchmarkCell(ProviderConfig):
    """Una celda del panel: un proveedor/modelo con su configuración de muestreo."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=_CELL_NAME_PATTERN)

    def to_provider_config(self) -> ProviderConfig:
        """La configuración de proveedor pura, sin el nombre de la celda.

        Se valida desde el volcado, no campo a campo: un campo nuevo de ``ProviderConfig``
        viaja sin tocar este método (revisión final de PR-0).
        """
        return ProviderConfig.model_validate(self.model_dump(exclude={"name"}))


class BenchmarkPanel(BaseModel):
    """Panel de celdas a comparar sobre el mismo corpus y el mismo gold."""

    model_config = ConfigDict(extra="forbid")

    name: str
    replicas: int = Field(default=1, ge=1)
    cells: list[BenchmarkCell] = Field(min_length=1)

    @model_validator(mode="after")
    def _nombres_unicos(self) -> BenchmarkPanel:
        vistos: set[str] = set()
        for celda in self.cells:
            if celda.name in vistos:
                raise ValueError(f"nombre de celda repetido: {celda.name!r}")
            vistos.add(celda.name)
        return self


def load_panel(path: str | Path) -> BenchmarkPanel:
    """Carga y valida un ``panel.yml``.

    Todo fallo se relanza como ``ValueError`` con la ruta: un solo tipo de error para el
    CLI (rc 2), sea YAML mal formado, clave de fusión, raíz que no es un mapa o esquema.
    """
    ruta = Path(path)
    try:
        with ruta.open(encoding="utf-8") as fh:
            rechazar_claves_de_fusion(fh, "panel.yml")
            fh.seek(0)
            crudo = yaml.safe_load(fh)
        if not isinstance(crudo, dict):
            raise ValueError("la raíz del panel debe ser un mapa")
        return BenchmarkPanel.model_validate(crudo)
    except (OSError, yaml.YAMLError, ValidationError, ValueError) as exc:
        raise ValueError(f"{path}: {exc}") from exc


class BenchmarkProtocolInfo(BaseModel):
    """Huella del protocolo, el corpus y el gold sobre los que se midió."""

    slug: str
    corpus_sha256: str
    gold_sha256: str
    n_records: int = Field(ge=0)
    n_gold_positives: int = Field(ge=0)


class BenchmarkCellResult(BaseModel):
    """Resultado de una réplica de una celda."""

    cell: str
    replica: int = Field(ge=1)
    run_dir: str  # relativa a la carpeta del benchmark, con "/"
    metrics: ScreeningMetrics
    recall_ci95: tuple[float, float] | None = None  # Wilson; None si el recall es indefinido
    models_used: list[str] = Field(default_factory=list)
    n_calls: int = Field(default=0, ge=0)
    n_failed_records: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _ic_acotado(self) -> BenchmarkCellResult:
        if self.recall_ci95 is not None:
            lo, hi = self.recall_ci95
            if not 0.0 <= lo <= hi <= 1.0:
                raise ValueError(
                    f"recall_ci95 debe cumplir 0 <= lo <= hi <= 1; recibido {(lo, hi)}"
                )
        return self


class BenchmarkResult(BaseModel):
    """``benchmark.json``: todas las celdas y réplicas de una comparación."""

    schema_version: int = ARTIFACT_SCHEMA_VERSION
    protocol: BenchmarkProtocolInfo
    environment: Environment
    cells: list[BenchmarkCellResult]
    created_utc: str = Field(default_factory=utc_now_iso)

    @model_validator(mode="after")
    def _celdas_unicas(self) -> BenchmarkResult:
        claves = [(c.cell, c.replica) for c in self.cells]
        if len(set(claves)) != len(claves):
            raise ValueError("pares (celda, réplica) repetidos")
        return self
