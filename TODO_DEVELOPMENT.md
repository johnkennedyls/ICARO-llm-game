# Plan de Desarrollo Continuado - El Escape de Ícaro

## 1. Documentación Técnica Completa
- [x] README.md profesional con instalación, ejecución, arquitectura
- [x] DOCS/architecture.md - Arquitectura de agentes, grafos, algoritmos
- [x] DOCS/algorithms.md - Análisis teórico/empírico de complejidad (Dijkstra, A*, predicción recursiva)
- [x] DOCS/agents.md - Detalle de cada agente (percepción, memoria, planificación, decisión)
- [x] DOCS/experiments.md - Guía de experimentos y análisis estadístico
- [x] DOCS/llm_integration.md - Documentación de agentes LLM
- [ ] Docstrings completos en todos los módulos públicos

## 2. Integración LLM (Agentes Impulsados por LLM) ✅ **COMPLETADO**
- [x] Módulo `icaro/llm_agents.py` - Base para agentes con LLM
- [x] Proveedor abstracto (OpenAI, Anthropic, local via Ollama, Mock)
- [x] Agente "Operador de Seguridad" - LLM que da pistas/habla con el jugador (tecla H)
- [x] Agente "Analista Táctico" - LLM que sugiere estrategias a ARGOS (auto)
- [x] Validación de acciones LLM contra reglas del juego (`LLMActionValidator`)
- [x] Separación de latencia LLM del tiempo de búsqueda algorítmica (async/asyncio)
- [x] Configuración de prompts y temperatura por agente
- [x] Cache de respuestas para reducir llamadas (hash de contexto)
- [x] Integración en Game.update() y App._handle_key (tecla H)
- [x] Determinismo: temperature=0, seed fija, caché por hash
- [x] Proveedores: OpenAI, Anthropic, Ollama, Mock (tests)
- [x] Configuración via .env (ver .env.example)

## 3. Mecánicas de Juego Avanzadas
- [ ] **Nuevos tipos de baldosas**:
  - [ ] Trampas (explosivas, aturdidoras, teletransportadoras)
  - [ ] Power-ups (escudo temporal, invisibilidad, velocidad, recarga energía)
  - [ ] Terminales especializadas (mapa completo, desactivar drones, abrir todas las puertas)
  - [ ] Conductos de ventilación (movimiento rápido, solo jugador)
  - [ ] Cámaras de seguridad (visión permanente, hackeables)
- [ ] **Modo sigilo**:
  - [ ] Medidor de ruido (correr vs caminar)
  - [ ] Distracciones (lanzar objetos, activar alarmas falsas)
  - [ ] Conos de visión dinámicos
- [ ] **Más variedad de mapas**:
  - [ ] Generador por "temas" (industrial, laboratorio, búnker, alcantarillas)
  - [ ] Mapas multinivel (escaleras/ascensores)
  - [ ] Eventos dinámicos (cortes de luz, inundaciones, incendios)
- [ ] **Nuevos objetivos**:
  - [ ] Rescatar rehenes
  - [ ] Recoger evidencia (logs, grabaciones)
  - [ ] Sabotear reactores

## 4. Agentes Más Sofisticados
- [ ] **ARGOS v2 - Aprendizaje de patrones**:
  - [ ] Memoria a largo plazo entre partidas (persistente)
  - [ ] Modelado del comportamiento del jugador (frecuencia rutas, riesgos)
  - [ ] Adaptación de dificultad dinámica
  - [ ] Predicción con árbol Monte Carlo (MCTS) opcional
- [ ] **Drones cooperativos v2**:
  - [ ] Formaciones (pinza, barrido, emboscada)
  - [ ] Comunicación enjambre (consenso distribuido)
  - [ ] Roles dinámicos (explorador, interceptor, centinela)
- [ ] **Nuevo agente: "Operador LLM"**:
  - [ ] Diálogos contextuales con el jugador
  - [ ] Pistas adaptativas según rendimiento
  - [ ] Narrativa emergente
- [ ] **Nuevo agente: "Analista Táctico LLM"**:
  - [ ] Sugiere bloqueos óptimos a ARGOS
  - [ ] Analiza patrones de movimiento globales
  - [ ] Coordina drones estratégicamente

## 5. Visualización y UX
- [ ] **Mini-mapa** (esquina, toggle con M)
- [ ] **Sistema de replay**:
  - [ ] Grabación completa de partidas
  - [ ] Reproducción con controles (play/pause/velocidad)
  - [ ] Exportar a video/GIF
- [ ] **Gráficas de métricas en vivo**:
  - [ ] Nodos expandidos por frame (sparkline)
  - [ ] Energía/seguridad/tiempo (historial)
  - [ ] Comparativa Dijkstra vs A* en tiempo real
- [ ] **HUD mejorado**:
  - [ ] Indicador de dirección a objetivo más cercano
  - [ ] Alertas visuales direccionales (ARGOS cerca, drone detectando)
  - [ ] Tooltips contextuales (F1 para ayuda)
- [ ] **Pantallas adicionales**:
  - [ ] Menú de configuración (gráficos, audio, dificultad)
  - [ ] Estadísticas históricas (partidas ganadas/perdidas, mejores tiempos)
  - [ ] Galería de replays

## 6. Experimentos y Análisis Avanzados
- [ ] **Más algoritmos para comparar**:
  - [ ] A* con heurísticas alternativas (Euclidiana, Chebyshev, Octile)
  - [ ] Jump Point Search (JPS)
  - [ ] LPA* (Lifelong Planning A*)
  - [ ] D* Lite
- [ ] **Escenarios experimentales adicionales**:
  - [ ] Mapas con diferentes densidades de obstáculos
  - [ ] Variación de costos de baldosas
  - [ ] Objetivos móviles vs estáticos
  - [ ] Múltiples agentes planificando simultáneamente
- [ ] **Exportación y visualización**:
  - [ ] Generar gráficas (matplotlib/seaborn) automáticamente
  - [ ] Dashboard HTML interactivo
  - [ ] Exportar a JSON/Parquet para análisis externo
- [ ] **Análisis estadístico**:
  - [ ] Pruebas de significancia (t-test, Mann-Whitney)
  - [ ] Intervalos de confianza
  - [ ] Análisis de escalabilidad (fit a complejidad teórica)

## 7. Empaquetado y Calidad
- [ ] pyproject.toml moderno (build, test, lint, type-check)
- [ ] GitHub Actions CI/CD (tests, lint, type-check, build)
- [ ] Ejecutable standalone (PyInstaller / Nuitka)
- [ ] Instalador Windows (NSIS) / AppImage Linux
- [ ] Versionado semántico + changelog
- [ ] Pre-commit hooks (ruff, mypy, black)