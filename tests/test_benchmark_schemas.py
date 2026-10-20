"""Panel y resultado de `revisia benchmark` (spec 2026-10-18 §4.2; D6, D23): solo modelos."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from revisia.llm.registry import ProviderConfig
from revisia.metrics import ScreeningMetrics
from revisia.schemas.artifacts import Environment
from revisia.schemas.benchmark import (
    BenchmarkCell,
    BenchmarkCellResult,
    BenchmarkPanel,
    BenchmarkProtocolInfo,
    BenchmarkResult,
    load_panel,
)

PANEL = """
name: panel-demo
replicas: 2
cells:
  - name: fake-a
    provider: fake
    model: fake-a
  - name: glm
    provider: zai
    model: glm-4.6
    temperature: 0.0
"""


def test_panel_carga_desde_yaml_y_las_celdas_son_provider_config(tmp_path: Path) -> None:
    path = tmp_path / "panel.yml"
    path.write_text(PANEL, encoding="utf-8")
    panel = load_panel(path)
    assert (panel.name, panel.replicas, [c.name for c in panel.cells]) == (
        "panel-demo",
        2,
        ["fake-a", "glm"],
    )
    cfg = panel.cells[1].to_provider_config()
    assert isinstance(cfg, ProviderConfig) and not isinstance(cfg, BenchmarkCell)
    assert (cfg.provider, cfg.model, cfg.temperature, cfg.effort) == ("zai", "glm-4.6", 0.0, None)


def test_to_provider_config_lleva_todos_los_campos_de_provider_config() -> None:
    # Todo campo de ProviderConfig (también uno que se añada mañana) viaja a la configuración.
    celda = BenchmarkCell(
        name="c",
        provider="claude_code",
        model="m",
        temperature=0.3,
        top_p=0.9,
        seed=7,
        effort="high",
    )
    cfg = celda.to_provider_config()
    assert cfg.model_dump() == celda.model_dump(exclude={"name"})
    assert set(cfg.model_dump()) == set(ProviderConfig.model_fields)


@pytest.mark.parametrize(
    "crudo",
    [
        {"name": "p", "cells": []},  # sin celdas
        {"name": "p", "replicas": 0, "cells": [{"name": "a", "provider": "fake", "model": "m"}]},
        {"name": "p", "cells": [{"name": "a", "provider": "fake", "model": "m"}] * 2},  # repetida
        {
            "name": "p",
            "cells": [{"name": "A b", "provider": "fake", "model": "m"}],
        },  # nombre no apto
        {"name": "p", "cells": [{"name": "a", "provider": "fake", "model": "m", "x": 1}]},  # extra
        {
            "name": "p",
            "cells": [{"name": "a", "provider": "fake", "model": "-x"}],
        },  # patrón de modelo
    ],
)
def test_panel_invalido_no_valida(crudo: dict) -> None:
    with pytest.raises(ValidationError):
        BenchmarkPanel.model_validate(crudo)


def test_load_panel_rechaza_claves_de_fusion(tmp_path: Path) -> None:
    path = tmp_path / "panel.yml"
    path.write_text(
        "base: &b {provider: fake, model: m}\nname: p\ncells:\n  - {<<: *b, name: a}\n", "utf-8"
    )
    with pytest.raises(ValueError, match="fusión"):
        load_panel(path)


def _entorno() -> Environment:
    return Environment(
        engine_version="0.9.0",
        python_version="3.13.0",
        python_implementation="CPython",
        platform="x",
        created_utc="2026-10-18T00:00:00+00:00",
    )


def _celda(**cambios) -> dict:
    base = {
        "cell": "fake-a",
        "replica": 1,
        "run_dir": "runs/fake-a-r1",
        "metrics": ScreeningMetrics(n=10, tp=4, fp=1, fn=1, tn=4, recall=0.8).model_dump(),
        "recall_ci95": (0.376, 0.964),
    }
    base.update(cambios)
    return base


def test_benchmark_result_celdas_unicas_e_ic_acotado() -> None:
    protocolo = BenchmarkProtocolInfo(
        slug="s", corpus_sha256="c" * 64, gold_sha256="g" * 64, n_records=10, n_gold_positives=5
    )
    ok = BenchmarkResult(
        protocol=protocolo, environment=_entorno(), cells=[BenchmarkCellResult(**_celda())]
    )
    assert ok.schema_version == 2 and ok.created_utc
    with pytest.raises(ValidationError):  # (celda, réplica) repetida
        BenchmarkResult(
            protocol=protocolo, environment=_entorno(), cells=[BenchmarkCellResult(**_celda())] * 2
        )
    with pytest.raises(ValidationError):
        BenchmarkCellResult(**_celda(recall_ci95=(0.9, 0.5)))
    with pytest.raises(ValidationError):
        BenchmarkCellResult(**_celda(recall_ci95=(0.0, 1.5)))
    assert BenchmarkCellResult(**_celda(recall_ci95=None)).recall_ci95 is None


@pytest.mark.parametrize("contenido", ["", "- a\n- b\n"])
def test_load_panel_raiz_que_no_es_mapa(tmp_path: Path, contenido: str) -> None:
    path = tmp_path / "panel.yml"
    path.write_text(contenido, encoding="utf-8")
    with pytest.raises(ValueError, match="panel.yml"):
        load_panel(path)


def test_load_panel_esquema_invalido_es_value_error_con_la_ruta(tmp_path: Path) -> None:
    path = tmp_path / "panel.yml"
    path.write_text("name: p\ncells: []\n", encoding="utf-8")
    with pytest.raises(ValueError, match="panel.yml") as exc:
        load_panel(path)
    assert type(exc.value) is ValueError


def test_load_panel_fichero_inexistente_es_value_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no-existe.yml"):
        load_panel(tmp_path / "no-existe.yml")


def test_temperature_por_defecto_es_cero() -> None:
    panel = BenchmarkPanel.model_validate(
        {"name": "p", "cells": [{"name": "a", "provider": "fake", "model": "m"}]}
    )
    assert panel.cells[0].temperature == 0.0
