# Política de seguridad

## Versiones soportadas

`prisma-loop` está en desarrollo temprano (`0.x`). Solo la última versión
publicada recibe correcciones de seguridad.

| Versión | Soportada |
|---------|-----------|
| 0.1.x   | ✅        |
| < 0.1   | ❌        |

## Reportar una vulnerabilidad

**No abras un issue público** para vulnerabilidades de seguridad.

Repórtalas en privado mediante **[GitHub Security Advisories](https://docs.github.com/es/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)**
(pestaña *Security → Report a vulnerability* de este repositorio). Incluye:

- Descripción de la vulnerabilidad y su impacto.
- Pasos para reproducirla.
- Versión afectada y entorno.

Te responderemos lo antes posible y coordinaremos una divulgación responsable.

## Manejo de credenciales y datos

`prisma-loop` habla con proveedores de IA externos y APIs académicas. Ten en
cuenta:

- **Nunca commitees** `.env`, API keys ni credenciales. El `.gitignore` ya
  excluye `.env`, los PDFs (`**/*.pdf`) y los `runs/` (salvo el manifiesto y los
  entregables). Verifícalo antes de cada push.
- **Gobernanza de datos sensibles (PRISMA-trAIce).** El corpus que revisas se
  envía al proveedor LLM que configures en `protocol.yml`. Si tu revisión maneja
  datos sensibles o no publicables, **configura un proveedor local**
  (`provider: local`, endpoint Ollama/vLLM/LM Studio) para que nada salga de tu
  máquina. El manifiesto registra qué proveedor procesó cada llamada.
- **Reproducibilidad ≠ exposición.** El `manifest.yml` guarda modelo, seed,
  temperatura y *hash* del prompt — nunca el contenido de tus credenciales.
