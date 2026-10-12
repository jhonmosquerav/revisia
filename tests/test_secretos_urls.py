"""Secretos en URLs firmadas y en la ``source_url`` de un texto recuperado.

Revisión final de la Ola 1, grupo B. Un repositorio en abierto redirige a menudo a una URL
prefirmada de su almacenamiento (S3, CloudFront, Azure SAS) con la firma en la query, y una URL
puede traer ``usuario:clave@``: ``redact_secrets`` no las tapaba y la ``source_url`` del texto
recuperado llegaba sin redactar a ``retrieval.jsonl`` y a la solicitud del gate FT. Además, la
suite no puede cargar el ``.env`` real del clon (una API key de la raíz entraba en pytest).
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from fakes import ScriptedProvider

from revisia import cli
from revisia.agents import _http
from revisia.agents.fulltext import FullText
from revisia.config import load_protocol
from revisia.orchestration import pipeline as pipeline_mod
from revisia.orchestration.pipeline import run_pipeline
from revisia.orchestration.run_context import RunContext
from revisia.schemas.records import SearchRecord

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "demo-mini-review"
SECRETO = "S3CR3TO-abc123"


@pytest.mark.parametrize(
    "parametro",
    [
        "X-Amz-Signature",
        "X-Amz-Credential",
        "X-Amz-Security-Token",
        "Signature",
        "Policy",
        "Key-Pair-Id",
        "sig",
        "secret",
        "client_secret",
        "password",
    ],
)
def test_redact_secrets_tapa_las_firmas_de_urls_prefirmadas(parametro: str) -> None:
    url = f"https://bucket.example/paper.pdf?a=1&{parametro}={SECRETO}&b=2"

    out = _http.redact_secrets(f"descargado de {url}")

    assert SECRETO not in out
    assert f"{parametro}=<redacted>&b=2" in out


def test_redact_secrets_tapa_el_userinfo_de_una_url() -> None:
    out = _http.redact_secrets(f"GET https://ana:{SECRETO}@repo.example/oa/1.pdf falló")

    assert SECRETO not in out and "ana" not in out
    assert out == "GET https://<redacted>@repo.example/oa/1.pdf falló"


@pytest.mark.parametrize(
    "texto",
    [
        "la firma (signature) del artículo y su policy brief",
        "https://repo.example/oa/1.pdf?page=2",
        "correo ana@example.org y la ruta //servidor/carpeta",
        "https://repo.example/a:b@c",  # `:` y `@` en la ruta, no en el userinfo
    ],
)
def test_redact_secrets_no_tapa_lo_que_no_es_secreto(texto: str) -> None:
    assert _http.redact_secrets(texto) == texto


@pytest.mark.parametrize(
    "texto",
    [
        "//" + "a" * 100_000 + ":" + "b" * 100_000,  # userinfo sin `@` final
        "sig" * 70_000,
        "x-amz-" * 35_000,
        "//a:" * 50_000,
        "key-pair-i" * 20_000,
    ],
    ids=["userinfo-sin-arroba", "sig", "x-amz", "barras-y-dos-puntos", "key-pair"],
)
def test_redact_secrets_sigue_siendo_lineal_con_200_000_caracteres(texto: str) -> None:
    inicio = time.perf_counter()
    _http.redact_secrets(texto)
    assert time.perf_counter() - inicio < 1.0


def test_source_url_del_texto_recuperado_se_redacta_antes_de_guardarla(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = f"https://ana:{SECRETO}@s3.example/p.pdf?X-Amz-Signature={SECRETO}&x=1"

    def fetch(_record: SearchRecord) -> FullText:
        return FullText(text="Texto completo del estudio.", available=True, source_url=url)

    def busqueda(_query: str, _n: int) -> list[SearchRecord]:
        return [SearchRecord(record_id="rec-1", title="LLM screening", source_db="OpenAlex")]

    monkeypatch.setattr(pipeline_mod, "build_provider", lambda _cfg: ScriptedProvider())
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")
    run_pipeline(protocol, EXAMPLE, ctx, auto_approve=True, search_fn=busqueda, fetch_fn=fetch)

    for rel in (
        "04_fulltext/retrieval.jsonl",
        "04_fulltext/retrieval.json",
        "screening_ft/review_request.yml",
    ):
        texto = (ctx.run_dir / rel).read_text(encoding="utf-8")
        assert SECRETO not in texto, rel
        assert "<redacted>" in texto, rel


def test_la_suite_no_carga_el_env_real(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Sin la marca `dotenv_real`, `main()` no lee ningún `.env` (conftest, B3).
    (tmp_path / ".env").write_text("REVISIA_PRUEBA_SIN_DOTENV=filtrada\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("REVISIA_PRUEBA_SIN_DOTENV", "provisional")
    monkeypatch.delenv("REVISIA_PRUEBA_SIN_DOTENV")

    assert cli.main(["brain", str(tmp_path / "sin-cerebro")]) == 1

    assert "REVISIA_PRUEBA_SIN_DOTENV" not in os.environ
