---
fuente: ProofreaderPro.ai (blog comercial de herramientas de escritura IA)
titulo: "Cómo utilizar la IA para una revisión sistemática que cumpla con PRISMA"
autor: "«Ema», presentada como PhD en Lingüística Computacional (probable persona editorial del sitio)"
fecha_publicacion: 2026-05-26
url: https://proofreaderpro.ai/es/blog/ai-prisma-systematic-review
url_version_inglesa: https://proofreaderpro.ai/blog/ai-prisma-systematic-review
fecha_consulta: 2026-07-05
tipo: blog-comercial-no-revisado
proyecto: revisia
etiquetas: [PRISMA, IA, revision-sistematica, cribado, transparencia, PRISMA-trAIce]
---

# IA + PRISMA en revisiones sistemáticas · extracto crítico del blog ProofreaderPro.ai

> **Advertencia de fuente**: blog comercial sin revisión por pares, publicado por un
> vendedor de herramientas de escritura con IA. El post existe en parte para enlazar
> sus propios productos (summarizer, proofreader, translator). Se extrae aquí lo
> metodológicamente útil; toda cifra se marca como afirmación del blog sin verificar.

## Resumen

Guía práctica sobre integración responsable de IA en revisiones sistemáticas PRISMA.
Tesis central: la IA acelera legítimamente cribado, extracción y traducción, pero las
decisiones vinculantes (inclusión final, riesgo de sesgo, GRADE, conclusiones) deben
seguir siendo humanas, y todo uso de IA debe divulgarse con herramienta + versión +
prompts + métricas de calibración. Propone un flujo de 10 pasos con ejercicio de
calibración previo (umbral κ ≥ 0,7 u 80 % de acuerdo) y se apoya en el checklist
PRISMA-trAIce (que resultó ser real y revisado por pares — ver sección dedicada).

## Qué exige PRISMA 2020 (repaso del blog)

Según el post, los requisitos documentales que la IA no exime:

- **Estrategia de búsqueda**: cada base de datos, cadena de búsqueda y fechas (reproducibilidad).
- **Cribado**: registros evaluados, número de revisores independientes, resolución de desacuerdos, exclusiones por etapa.
- **Extracción de datos**: qué se extrajo, quién, cómo se resolvieron discrepancias.
- **Riesgo de sesgo**: herramienta usada (Cochrane RoB 2, ROBINS-I…) y responsables.
- **Desviaciones**: todo lo que diverja del protocolo preregistrado se reporta fundamentadamente.

## Dónde ayuda legítimamente la IA (según el blog)

1. **Deduplicación** — aunque señala que los gestores tradicionales (Zotero, EndNote, Covidence) ya lo hacen bien.
2. **Cribado título/resumen** — la IA califica cada resumen contra los criterios de inclusión y los preclasifica/prioriza (nunca decide).
3. **Recuperación y clasificación de texto completo** — extraer metadatos, comprobar si el texto completo coincide con lo que afirma el resumen.
4. **Extracción de datos estructurados** — valores candidatos desde PDFs a la hoja de extracción.
5. **Soporte de síntesis y redacción** — ayuda con la prosa "sin cambiar el contenido".
6. **Traducción de fuentes no inglesas** — "lo suficientemente confiable como para respaldar la inclusión" (afirmación del blog, sin verificar).

## Dónde la IA NO debe hacer el trabajo (según el blog)

1. **Decisiones finales de inclusión/exclusión** — "La decisión vinculante debe ser humana. Esto no es negociable."
2. **Evaluación de riesgo de sesgo** — la calificación en sí debe ser humana.
3. **Evaluación de calidad / GRADE** — califican humanos.
4. **Interpretación de heterogeneidad** — requiere experiencia clínica y metodológica.
5. **Síntesis final y conclusiones** — "los juicios de fondo son suyos".
6. **Detección de contenido fabricado / paper mills** — "la detección por IA de estudios fabricados sigue siendo poco fiable" (afirmación del blog, sin verificar); el estándar actual sería ojos humanos + herramientas como Problematic Paper Screener.

## Flujo de trabajo recomendado (10 pasos)

| # | Paso | La IA automatiza | Queda para el humano |
|---|------|------------------|----------------------|
| 1 | Registro previo del protocolo (PROSPERO / OSF) | Nada | Criterios de inclusión, estrategia de búsqueda, método de cribado **y dónde se usará IA** |
| 2 | Ejercicio de calibración | Criba/clasifica 100–200 resúmenes con el prompt planificado | Dos revisores criban el mismo set a ciegas; se calcula κ de Cohen; si κ < 0,7 o acuerdo < 80 %, se refina el prompt |
| 3 | Cribado principal con IA | Examina todo el corpus con el prompt calibrado, produce lista clasificada/priorizada | Supervisión; el output es solo priorización |
| 4 | Evaluación independiente por dos revisores | Nada — "la clasificación de la IA son metadatos, no una votación" | Cada resumen lo criban dos humanos; desacuerdos por discusión o tercer revisor |
| 5 | Cribado de texto completo asistido | Marca exclusiones obvias (idioma incorrecto, solo abstract, retractados) | Decisiones finales de elegibilidad |
| 6 | Extracción de datos asistida | Extrae valores candidatos de PDFs (características de pacientes, dosis, tamaños de efecto) | Dos revisores verifican TODOS los valores contra la fuente original |
| 7 | Riesgo de sesgo | **Ninguna — "No hay IA en este paso"** | RoB 2 / ROBINS-I aplicados por humanos |
| 8 | Síntesis con dirección humana | Resume estudios, borrador de métodos, ayuda con prosa | Interpretación de heterogeneidad, implicaciones clínicas, síntesis narrativa |
| 9 | Divulgación exhaustiva | Nada | Métodos con prompts exactos, métricas de calibración, limitaciones; declaración de uso de IA visible |
| 10 | Auditoría pre-publicación | Nada | Un segundo miembro del equipo audita los pasos asistidos por IA: versiones, prompts faltantes, % de verificación |

## Inventario de herramientas mencionadas

El blog es **pobre en herramientas de terceros** — no menciona ASReview, Elicit,
DistillerSR, RobotReviewer, Covidence-AI ni ningún LLM concreto (GPT/Claude/Gemini);
habla genéricamente de "modelos de lenguaje modernos". Lo que sí nombra:

| Herramienta | Etapa | Naturaleza | Notas |
|-------------|-------|------------|-------|
| Zotero | Deduplicación / gestión de referencias | Open source (el blog no lo etiqueta) | Mencionada como estándar |
| EndNote | Deduplicación / gestión de referencias | Comercial (el blog no lo etiqueta) | — |
| Covidence | Cribado por pares y extracción | Comercial (el blog no lo etiqueta) | Registro de decisiones humanas |
| Rayyan | Cribado por pares y extracción | Freemium (el blog no lo etiqueta) | Registro de decisiones humanas |
| Problematic Paper Screener | Detección de papers fabricados | Gratuita (el blog no lo etiqueta) | "Estándar actual" junto a revisión humana |
| PROSPERO | Registro de protocolo (médicas) | Registro público | — |
| OSF | Registro de protocolo (otras disciplinas) | Plataforma abierta | — |
| Cochrane RoB 2 / ROBINS-I | Riesgo de sesgo | Instrumentos metodológicos | Solo humanos |
| ProofreaderPro AI Summarizer | Resumen de estudios / redacción | **Producto propio del sitio** | `/ai-summarizer` |
| ProofreaderPro AI Proofreader | Pulido de prosa | **Producto propio** | `/ai-proofreader` |
| ProofreaderPro Text Humanizer | Reescritura | **Producto propio** | `/text-humanizer` |
| ProofreaderPro Paraphrasing Tool | Paráfrasis | **Producto propio** | `/paraphrasing-tool` |
| ProofreaderPro AI Translator | Traducción de fuentes no inglesas | **Producto propio** | `/ai-translator` |

Las clasificaciones open source/comercial de la tabla son mías, no del blog (el blog no clasifica ninguna).

## PRISMA-trAIce — verificado como REAL

El blog apoya sus requisitos de reporte en **PRISMA-trAIce** ("PRISMA – Transparent
Reporting of Artificial Intelligence in Comprehensive Evidence Synthesis").
Verificación independiente (2026-07-05): **existe y es peer-reviewed**:

- Paper: "Transparent Reporting of AI in Systematic Literature Reviews: Development of the PRISMA-trAIce Checklist", **JMIR AI, 2025;1:e80247** — https://ai.jmir.org/2025/1/e80247 · PMC: https://pmc.ncbi.nlm.nih.gov/articles/PMC12694947/
- Checklist de **12 ítems**: identificación de herramientas, interacción humano-IA, reporte de prompts, métricas de calibración/rendimiento, procedimientos de verificación humana, limitaciones. Agnóstico de disciplina, extensión de PRISMA 2020.
- Distinción clave (coincide blog y paper): **PRISMA-AI** aplica cuando la IA es el *objeto* de la revisión; **PRISMA-trAIce** cuando la IA es *herramienta metodológica* de la revisión.
- Discrepancia menor: el blog dice "publicada en 2024, actualizada en 2025"; la publicación en JMIR AI es de 2025 (posible confusión con el preprint).

**Para revisia: el paper de JMIR AI es la fuente primaria a incorporar; el blog es solo divulgación derivada.**

## Buenas prácticas y requisitos de divulgación (según el blog)

- **Regla general**: en cualquier punto donde se use IA, reportar herramienta, versión, rango de fechas, rol específico, prompts exactos y cómo se hizo la verificación humana.
- **Prompts al apéndice**: "Indicaciones utilizadas se proporcionan en el Apéndice".
- **Declarar el negativo**: indicar explícitamente que la IA NO se usó para decisiones finales, RoB, GRADE ni conclusiones.
- **Calibración previa obligatoria**: reportar el ejercicio de calibración (nº de resúmenes, κ, % acuerdo).
- **Documentar cambios de prompt a mitad de revisión**: motivo + re-cribar los elementos afectados.
- **Limitaciones a reconocer**: posible sesgo sistemático en la preclasificación; opacidad interna de las herramientas; imposibilidad de reproducir exactamente el comportamiento del modelo entre versiones.
- **Diagrama de flujo PRISMA**: los resúmenes cribados con ayuda de IA pueden entrar, con nota de atribución (ver plantilla abajo).
- **Cómo citar una herramienta de IA**: "[Nombre del modelo], versión [X.Y], accedido [fechas] a través de [API/interfaz web]" + desarrollador y documentación.

## Plantillas y textos modelo que propone

(Traducciones del blog, redacción algo tosca en la versión ES; útiles como esqueleto.)

**Métodos · cribado:**
> "La selección de resúmenes se realizó mediante un proceso de dos etapas. La clasificación inicial se realizó utilizando [Nombre de la herramienta, versión, accedida vía API/web en fechas] con la siguiente plantilla de prompt: '[prompt exacto]'. La clasificación se utilizó para priorizar los resúmenes para la revisión humana. Todos los resúmenes, independientemente de la clasificación inicial, fueron examinados de forma independiente por dos revisores. La clasificación de la IA coincidió con la decisión humana de consenso en el [porcentaje]% de los casos."

**Métodos · extracción de datos:**
> "La extracción de datos se realizó mediante un formulario estructurado (Apéndice [X]). La extracción de [tipos de datos] fue respaldada por [Herramienta, versión], que extrajo valores candidatos de los PDFs de texto completo. Todos los valores extraídos fueron verificados contra los PDFs de origen por dos revisores ([iniciales])."

**Métodos · subsección "Uso de IA":**
> "En esta revisión se utilizaron las siguientes herramientas de IA: [cada herramienta, versión, rango de fechas y rol específico]. No se utilizó ninguna herramienta de IA para la evaluación del riesgo de sesgo, la calificación de la calidad, la interpretación de la heterogeneidad o la síntesis de conclusiones."

**Nota para el diagrama de flujo PRISMA:**
> "Se utilizó clasificación inicial respaldada por IA para priorizar los resúmenes; todos los resúmenes recibieron evaluación humana independiente por parte de dos revisores."

## Afirmaciones cuantitativas (afirmaciones del blog, SIN VERIFICAR)

- "Una revisión sistemática solía llevar a un equipo de tres investigadores de seis a nueve meses" (anécdota de apertura, sin fuente).
- La IA "reduce la fase de selección de una revisión de meses a semanas" (sin fuente ni estudio citado).
- Escenario de apertura: "Doce mil resúmenes extraídos de PubMed, Embase, Scopus y Cochrane" con doble revisor (ilustrativo, no un caso documentado).
- Umbral de calibración: κ ≥ 0,7 o acuerdo ≥ 80 % IA-vs-consenso humano sobre 100–200 resúmenes (umbral razonable pero el blog no cita de dónde sale).
- PRISMA-trAIce: 12 ítems (esto SÍ coincide con el paper de JMIR AI).
- No da tasas de error de la IA, precisión/recall de cribado ni datos de rendimiento propios.

## Errores comunes que señala (causas de rechazo editorial)

1. **Características alucinadas** — la IA extrae datos que no están en el artículo original (n incorrectos, detalles fabricados). Mitigación: verificar todo valor contra la fuente.
2. **Cambios de prompt sin documentar** — alterar el prompt a mitad de revisión cambia el comportamiento; hay que documentar el motivo y re-cribar lo afectado.
3. **Delegación indebida** — tratar la clasificación de la IA como vinculante cuando PRISMA exige decisión humana final.
4. **Desviaciones omitidas** — no reportar cambios sobre el protocolo preregistrado; "los cambios de proceso ocultos se señalan en la revisión por pares".
5. (De la lista de rechazo) **Asumir la precisión de la traducción sin verificarla** y **versiones de herramientas inconsistentes** entre métodos y apéndices.

## FAQ del post (resumen)

- **¿Resúmenes cribados por IA en el diagrama PRISMA?** Sí, con nota de atribución y doble revisión humana.
- **¿Cómo citar herramientas de IA?** Modelo + versión + fechas de acceso + vía (API/web) + desarrollador.
- **¿PRISMA 2020 vs PRISMA-trAIce?** 2020 es el estándar general; trAIce añade los 12 ítems específicos para pasos asistidos por IA.
- **¿Usar IA reduce la aceptación del manuscrito?** Según el blog, no si está divulgado y documentado; lo que daña es el uso oculto o la sustitución del juicio humano requerido.

## Valoración crítica

**Fiabilidad: media-baja como fuente; media-alta como índice de temas.** Es contenido
SEO de un vendedor de herramientas de escritura: sin referencias bibliográficas, sin
enlaces externos, autora probablemente persona editorial ("Ema, PhD"), y cinco de las
trece herramientas mencionadas son productos del propio sitio (el "AI Translator" y el
"Summarizer" propios se presentan donde cabrían herramientas especializadas de SR).
La versión en español es traducción automática visiblemente tosca.

**Lo que sí vale.** (1) El marco decisional "dónde sí / dónde no" y el flujo de 10 pasos
son ortodoxos y coinciden con la práctica Cochrane (doble revisor, IA como priorización
y no votación, RoB 100 % humano); son directamente reutilizables como diseño de
salvaguardas en revisia. (2) El hallazgo mayor de esta extracción: **PRISMA-trAIce
existe y es peer-reviewed (JMIR AI 2025;1:e80247)** — verificado por búsqueda
independiente; revisia debería ingerir ese paper como fuente primaria y mapear sus
12 ítems contra los reportes que genera el motor. (3) Las plantillas de divulgación de
métodos son esqueletos útiles y fáciles de adaptar. (4) El ejercicio de calibración con
umbral κ ≥ 0,7 / 80 % es operacionalizable en revisia como gate automático.

**Lo que hay que contrastar con fuentes revisadas antes de usar:** el umbral κ 0,7/80 %
sobre 100–200 resúmenes (¿de dónde sale? contrastar con literatura de ASReview,
Cochrane RAISE y estudios de cribado semiautomatizado); la afirmación "traducción IA
suficientemente confiable para respaldar inclusión"; "de meses a semanas"; y la fecha
"2024" de PRISMA-trAIce (el paper es 2025). El inventario de herramientas de terceros
es casi inexistente — para un catálogo real de tooling SR, buscar fuentes dedicadas
(ASReview, Elicit, DistillerSR, RobotReviewer no aparecen aquí).

Fuentes de verificación:
- [PRISMA-trAIce en JMIR AI](https://ai.jmir.org/2025/1/e80247)
- [PRISMA-trAIce en PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12694947/)
- [Versión inglesa del post](https://proofreaderpro.ai/blog/ai-prisma-systematic-review)
