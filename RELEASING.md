# Publicación y releases

Este repositorio es la **fuente canónica** de `revisia`. Esta guía describe
cómo liberar una versión y obtener un DOI citable.

## 1 · Bump de versión

La versión vive en tres archivos; deben coincidir:

- `pyproject.toml` → `version = "X.Y.Z"`
- `revisia/__init__.py` → `__version__ = "X.Y.Z"`
- `CITATION.cff` → `version: "X.Y.Z"` y `date-released: "YYYY-MM-DD"`

Añade la entrada correspondiente en `CHANGELOG.md` (mueve lo de `Unreleased`).

## 2 · DOI vía Zenodo (apertura científica)

1. Inicia sesión en [Zenodo](https://zenodo.org) con tu cuenta de GitHub.
2. En *Settings → GitHub*, activa el webhook para el repo `revisia`.
3. El archivo [`.zenodo.json`](.zenodo.json) ya define los metadatos del depósito
   (título, autoría, licencia Apache-2.0, keywords).
4. Crea un **GitHub Release** (`git tag vX.Y.Z` → publica el release). Zenodo
   archiva automáticamente ese tag y emite un DOI.
5. Pega el **DOI concept** (todas las versiones) en:
   - `CITATION.cff` → descomenta el bloque `identifiers` y rellénalo.
   - El badge de DOI del `README.md`.

## 3 · Checklist de release

- [ ] Versiones sincronizadas en los tres archivos.
- [ ] `CHANGELOG.md` actualizado.
- [ ] `uv run pytest -q` verde · `ruff` + `black` limpios.
- [ ] `uv build` produce sdist + wheel sin errores.
- [ ] Tag `vX.Y.Z` creado y release publicado.
- [ ] DOI de Zenodo incorporado a `CITATION.cff` y README.
