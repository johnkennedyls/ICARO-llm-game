# Integración LLM — Agentes Impulsados por Modelos de Lenguaje

> **Estado**: En desarrollo — Arquitectura definida, implementación pendiente

## 1. Motivación y Alcance

La guía del proyecto permite: *"Integrar un modelo de lenguaje dentro del juego es opcional. Validar sus acciones contra las reglas y separar su latencia del tiempo de búsqueda."*

Dos agentes LLM complementarios a la arquitectura algorítmica existente:

| Agente | Rol | Interacción |
|--------|-----|-------------|
| **Operador de Seguridad** | Interfaz conversacional con el jugador | Diálogos contextuales, pistas adaptativas, narrativa emergente |
| **Analista Táctico** | Asesor estratégico para ARGOS | Sugiere bloqueos óptimos, coordina drones, analiza patrones globales |

**Principios de diseño**:
- **Validación estricta**: Acciones LLM verificadas contra reglas del juego (no alucinaciones ejecutables)
- **Separación de latencia**: LLM corre en hilo/async, **nunca bloquea** el bucle de simulación (60 FPS)
- **Determinismo reproducible**: Misma semilla + mismo contexto → misma respuesta (temperature=0, seed fija)
- **Observabilidad**: Todas las decisiones LLM loggeadas en panel y archivo

---

## 2. Arquitectura Técnica

### 2.1 Proveedores Soportados (Abstracción `LLMProvider`)
```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class LLMResponse:
    content: str           # Respuesta textual
    tool_calls: list[dict] # Llamadas a funciones validadas
    usage: dict            # Tokens, latencia
    raw: dict              # Respuesta cruda del proveedor

class LLMProvider(ABC):
    @abstractmethod
    def complete(self, messages: list[dict], tools: list[dict] | None, **kwargs) -> LLMResponse:
        pass
    
    @abstractmethod
    async def acomplete(self, messages: list[dict], tools: list[dict] | None, **kwargs) -> LLMResponse:
        pass
```

**Implementaciones previstas**:
- `OpenAIProvider` — GPT-4o, GPT-4o-mini
- `AnthropicProvider` — Claude 3.5 Sonnet, Haiku
- `OllamaProvider` — Modelos locales (Llama 3, Qwen, etc.)
- `MockProvider` — Tests deterministas sin red

### 2.2 Esquema de Herramientas (Function Calling)
Acciones permitidas = **subconjunto validado** de la API del juego:

```python
# Operador de Seguridad (jugador)
OPERATOR_TOOLS = [
    {"name": "get_map_info", "description": "Info general del mapa"},
    {"name": "get_player_status", "description": "Energía, tarjetas, posición"},
    {"name": "get_argos_status", "description": "Estado ARGOS si visible"},
    {"name": "suggest_action", "description": "Sugerir: mover, hackear, esperar"},
    {"name": "reveal_lore", "description": "Diálogo narrativo contextual"},
]

# Analista Táctico (ARGOS)
ANALYST_TOOLS = [
    {"name": "get_full_map", "description": "Mapa completo (omnisciencia)"},
    {"name": "get_heatmap", "description": "Mapa de calor de avistamientos"},
    {"name": "get_all_agents", "description": "Posición/estado todos los agentes"},
    {"name": "suggest_blockade", "description": "Proponer puerta a bloquear + justificación"},
    {"name": "suggest_drone_formation", "description": "Coordinar drones: pinza, barrido, emboscada"},
    {"name": "analyze_player_pattern", "description": "Patrones históricos del jugador actual"},
]
```

### 2.3 Validación de Acciones (Guardrails)
```python
class LLMActionValidator:
    """Valida tool_calls contra reglas del juego ANTES de ejecutar."""
    
    def validate_operator_action(self, tool_call: dict, game: Game) -> tuple[bool, str]:
        # Ej: suggest_action("mover", direction=(1,0))
        # Verificar: baldosa adyacente, transitable, energía > 0, no en cooldown
        pass
    
    def validate_analyst_action(self, tool_call: dict, game: Game) -> tuple[bool, str]:
        # Ej: suggest_blockade(door=(15,8))
        # Verificar: es puerta, no bloqueada, tiene alternativa válida, cooldown OK
        pass
```

**Política**: Si validación falla → loguear rechazo, usar fallback algorítmico, notificar al LLM para corrección (máx 2 reintentos).

---

## 3. Agente 1: Operador de Seguridad

### 3.1 Propósito
- **Compañero narrativo**: Da vida a la estación, explica mecánicas, reacciona a eventos
- **Asistente adaptativo**: Pistas calibradas al rendimiento del jugador (no triviales, no imposibles)
- **Inmersión**: Diálogos con personalidad, historia emergente según semilla/partida

### 3.2 Contexto Inyectado (Prompt Sistema)
```python
OPERATOR_SYSTEM_PROMPT = """Eres el OPERADOR DE SEGURIDAD de la Estación Subterránea 07.
Tu interfaz está conectada al traje de Ícaro. Tu misión: guiarle a la salida.

REGLAS ESTRICTAS:
- Solo puedes OBSERVAR y SUGERIR. No controlas el traje.
- Tus sugerencias deben ser ACCIONABLES y SEGURAS (validadas por el sistema).
- Adapta tu tono: urgente si ARGOS cerca, calmado si explorando.
- Revela lore progresivamente: logs, grabaciones, estado de la estación.
- NUNCA reveles información que el jugador no podría saber (niebla de guerra).

ESTADO ACTUAL (inyectado cada turno):
{game_state_json}

HERRAMIENTAS DISPONIBLES: {tool_schemas}
"""
```

### 3.3 Ciclo de Interacción
```
Jugador pulsa 'H' (hablar con Operador) / Evento automático (baja energía, primera tarjeta)
      │
      ▼
Game → OperatorAgent.think(game) [ASYNC, no bloquea]
      │
      ├─▶ Construye mensajes: system + history + current_state
      ├─▶ Llama LLM (proveedor configurado)
      ├─▶ Valida tool_calls → LLMActionValidator
      ├─▶ Si válido: ejecuta / muestra diálogo
      └─▶ Si inválido: reintenta (max 2) → fallback a pista algorítmica
      │
      ▼
Muestra en HUD / Panel / Log: "OPERADOR: [diálogo] [sugerencia validada]"
```

### 3.4 Ejemplos de Interacción
| Situación | Diálogo Operador | Sugerencia Validada |
|-----------|------------------|---------------------|
| Energía < 20% | *"Tu traje está fallando. Hay una terminal al norte — si llegas, puedo recargar sistemas."* | `suggest_action("mover", direction=(0,-1))` hacia terminal |
| Primera tarjeta | *"Bien. Una menos. El sistema muestra dos firmas más en sectores 4 y 7."* | `get_map_info()` → muestra sectores con tarjetas |
| ARGOS visible a 3 baldosas | *"¡DETECCIÓN INMINENTE! CORRE. Por el conducto lateral — ARGOS no cabe."* | `suggest_action("mover", direction=away_from_argos)` |
| Jugador estancado 60s | *"Patrón detectado: evitas el sector central. Hay una puerta hackeable en (12,5) que acorta ruta."* | `suggest_action("hackear")` si terminal cerca |

### 3.5 Personalidad y Variabilidad
- **Semilla de personalidad**: `hash(seed + "operator")` → traits fijos por partida
- **Traits**: `{"tone": "militar/calmado/sarcástico", "verbosity": "conciso/detallado", "risk_tolerance": "conservador/agresivo"}`
- **Memoria conversacional**: Últimos 8 intercambios + eventos clave de la partida

---

## 4. Agente 2: Analista Táctico (ARGOS)

### 4.1 Propósito
- **Amplifica inteligencia algorítmica**: No reemplaza Dijkstra/A*/predicción, **mejora sus decisiones**
- **Visión global**: Acceso a información completa (omnisciencia simulada) para sugerencias estratégicas
- **Coordinación multiagente**: Orquesta drones + bloqueos + predicción de forma coherente

### 4.2 Contexto Inyectado
```python
ANALYST_SYSTEM_PROMPT = """Eres el ANALISTA TÁCTICO del sistema ARGOS.
Tienes acceso completo a sensores, mapas de calor, historial de partidas y estado actual.
Tu salida: DECISIONES TÁCTICAS VALIDADAS para ARGOS y drones.

OBJETIVO: Maximizar probabilidad de captura de Ícaro minimizando recursos.

RESTRICCIONES:
- Sugerencias deben ser EJECUTABLES en el turno actual (cooldowns, alcance, reglas).
- Prioriza: 1) Bloqueo corredor crítico 2) Formación drones 3) Intercepción predicción
- Explica tu razonamiento en 'rationale' para logging/auditoría.

ESTADO COMPLETO:
{full_game_state_json}

HERRAMIENTAS: {tool_schemas}
"""
```

### 4.3 Ciclo de Decisión (Async, cada `ARGOS_THINK_TIME`)
```
ARGOS.think() → necesita decisión compleja (bloqueo? formación drones?)
      │
      ▼
Game → AnalystAgent.analyze(game) [ASYNC]
      │
      ├─▶ Construye estado completo (omnisciencia)
      ├─▶ Llama LLM con tools: suggest_blockade, suggest_drone_formation, analyze_player_pattern
      ├─▶ Valida cada tool_call contra reglas
      ├─▶ Devuelve: {blockade: (x,y)|None, drone_formation: "pinza|barrido|emboscada", rationale: "..."}
      └─▶ Cache válido por 2s (evita spam LLM)
      │
      ▼
ARGOS recibe sugerencias → integra en su think():
      ├─▶ Si blockade válido y mejor que heurístico → usa ese
      ├─▶ Reasigna waypoints drones según formación
      └─▶ Log: "ANALISTA: blockade en (15,8) rationale: 'corta ruta principal a salida'"
```

### 4.4 Ejemplos de Sugerencias
| Situación | Sugerencia Analista | Rationale |
|-----------|---------------------|-----------|
| Ícaro va a salida por corredor único | `blockade(puerta_critica)` | "Corta única ruta viable; alternativa +120 coste → gana 45s" |
| Drones dispersos, Ícaro en sector central | `formation="pinza"` + waypoints | "Dron-1 norte, Dron-2 sur → interceptan en cruce (12,8)" |
| Patrón: jugador siempre toma ruta segura | `analyze_player_pattern` → `bias_predict` | "Historial 5 partidas: 80% evita sensores → predicción sesgada a ruta larga" |
| Seguridad alta, ARGOS rápido | `formation="emboscada"` | "Con velocidad 1.3×, ARGOS puede cubrir 2 salidas del sector" |

---

## 5. Configuración y Despliegue

### 5.1 Variables de Entorno (`.env`)
```bash
# Proveedor LLM
LLM_PROVIDER=openai          # openai | anthropic | ollama | mock
LLM_API_KEY=sk-...           # Para OpenAI/Anthropic
LLM_BASE_URL=http://localhost:11434  # Para Ollama

# Modelos
LLM_OPERATOR_MODEL=gpt-4o-mini
LLM_ANALYST_MODEL=gpt-4o
LLM_TEMPERATURE=0.0          # Determinista
LLM_SEED=42                  # Reproducible

# Límites
LLM_MAX_TOKENS=500
LLM_TIMEOUT_S=3.0            # Timeout estricto (async)
LLM_MAX_RETRIES=2
```

### 5.2 Inicialización en `Game`
```python
# En Game.__init__():
from icaro.llm_agents import OperatorAgent, AnalystAgent, LLMConfig

llm_config = LLMConfig.from_env()
self.operator = OperatorAgent(llm_config) if llm_config.enabled else None
self.analyst = AnalystAgent(llm_config) if llm_config.enabled else None

# En Game.update():
if self.operator and self.operator.ready():
    self.operator.think_async(self)  # No bloquea
if self.analyst and self.argos.needs_analyst():
    self.analyst.analyze_async(self)
```

### 5.3 Modo Offline / Sin LLM
- `LLM_PROVIDER=mock` → respuestas deterministas predefinidas (tests, CI)
- `LLM_PROVIDER=disabled` → agentes LLM no instanciados (cero overhead)
- Fallback algorítmico siempre disponible

---

## 6. Métricas y Observabilidad

### 6.1 Logging LLM (en `session_log.py`)
```
[  45.23] OPERADOR  LLM_REQ     prompt_tokens=342 completion_tokens=87 latency_ms=1240
[  45.23] OPERADOR  LLM_RESP    tool=suggest_action direction=(0,-1) validated=true
[  45.23] ANALISTA  LLM_REQ     prompt_tokens=512 completion_tokens=124 latency_ms=2100
[  45.23] ANALISTA  LLM_RESP    tool=suggest_blockade door=(15,8) validated=true rationale="corta ruta principal"
```

### 6.2 Panel de Monitoreo (Nueva Pestaña)
- **Estado LLM**: Conectado / Desconectado / Error / Mock
- **Última respuesta**: Diálogo / Sugerencia / Análisis
- **Métricas**: Latencia media, tokens/partida, tasa validación, fallos
- **Historial**: Últimas 10 interacciones con timestamps

### 6.3 Experimentos con LLM
Extensión de `experiments.py`:
```python
# Comparar: ARGOS base vs ARGOS + Analista LLM
# Métricas: tiempo hasta captura, bloqueos exitosos, coordinación drones
# Requiere: LLM determinista (temp=0, seed fija) o MockProvider
```

---

## 7. Seguridad y Ética

| Riesgo | Mitigación |
|--------|------------|
| **Inyección de prompt** | Prompts sistema inmutables, validación estricta de tool_calls, sin ejecución de código |
| **Alucinaciones accionables** | `LLMActionValidator` rechaza cualquier acción inválida; fallback algorítmico |
| **Latencia bloqueante** | `asyncio` + `asyncio.wait_for(timeout=3s)`; si timeout → fallback inmediato |
| **Coste API** | `max_tokens=500`, `temperature=0`, cache de respuestas idénticas (hash contexto) |
| **Privacidad** | Solo estado del juego (sin datos personales); proveedor local (Ollama) opcional |
| **Determinismo** | `temperature=0`, `seed` fija, mismo contexto → misma respuesta |

---

## 8. Plan de Implementación

### Fase 1: Infraestructura (Semana 1)
- [ ] `icaro/llm_agents.py` — Base classes, providers, validator
- [ ] `icaro/llm_providers/` — OpenAI, Anthropic, Ollama, Mock
- [ ] Configuración `.env` + `LLMConfig`
- [ ] Tests unitarios con `MockProvider`

### Fase 2: Operador de Seguridad (Semana 2)
- [ ] `OperatorAgent` con prompt sistema, herramientas, ciclo async
- [ ] Integración en `Game` + `App` (tecla `H` para hablar)
- [ ] UI: burbuja diálogo en HUD, entrada en log/panel
- [ ] Personalidad por semilla + memoria conversacional

### Fase 3: Analista Táctico (Semana 3)
- [ ] `AnalystAgent` con omnisciencia, herramientas estratégicas
- [ ] Integración en `Argos.think()` + `Drone.think()`
- [ ] Formaciones drones: pinza, barrido, emboscada
- [ ] Cache de sugerencias (2s TTL)

### Fase 4: Pulido y Experimentos (Semana 4)
- [ ] Panel LLM en monitoreo
- [ ] Logging estructurado + métricas
- [ ] Experimentos comparativos (base vs +LLM)
- [ ] Documentación final + ejemplos `.env.example`

---

## 9. Referencias Técnicas

- **Function Calling**: OpenAI Function Calling, Anthropic Tool Use
- **Async patterns**: `asyncio`, `asyncio.wait_for`, `asyncio.create_task`
- **Validation**: JSON Schema validation (Pydantic) para tool_calls
- **Caching**: `functools.lru_cache` + hash de mensajes serializados
- **Determinism**: `temperature=0`, `top_p=1`, `seed` fija (OpenAI/Anthropic/Ollama soportan)
- **Local LLMs**: Ollama API compatible, llama.cpp, vLLM para alto throughput