## Qué cambia y por qué

<!-- Describe el cambio y la motivación. Enlaza el issue si aplica (Closes #N). -->

## Checklist

- [ ] `uv run pytest -q` verde (offline, sin API key).
- [ ] `uv run ruff check .` limpio.
- [ ] `uv run black --check .` limpio.
- [ ] Commit(s) en **Conventional Commits** (`feat:`, `fix:`, `docs:`, …).
- [ ] Se respeta **HITL**: ningún cambio automatiza una decisión metodológica
      saltándose el checkpoint humano ni sube la autonomía por encima de A1.
- [ ] Se respeta **motor ↔ config**: no se mezclan datos de una revisión con el motor.
- [ ] Si añade/modifica un proveedor LLM, el núcleo sigue importándose sin su SDK.
- [ ] Si cambia un prompt, se subió la versión en `prisma_loop/prompts/<etapa>/vN.md`.
- [ ] No se incluyen `.env`, API keys, PDFs con copyright ni datos de terceros.
