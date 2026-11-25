"""Integración LLM para agentes conversacionales y tácticos.

Arquitectura:
- LLMProvider (ABC) → OpenAI, Anthropic, Ollama, Mock
- LLMActionValidator → Valida tool_calls contra reglas del juego
- OperatorAgent → Operador de Seguridad (diálogo con jugador)
- AnalystAgent → Analista Táctico (asesor para ARGOS/drones)
- Async execution con timeout estricto, nunca bloquea bucle principal.

Configuración vía variables de entorno (ver .env.example).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from functools import lru_cache
from typing import Any, Callable, Awaitable, Optional, TYPE_CHECKING
from pathlib import Path

# Imports condicionales para evitar importaciones circulares
if TYPE_CHECKING:
    from .game import Game
    from .graph import Coord
    from .maze import Maze

try:
    from . import config
except ImportError:
    # Para ejecución standalone / tests
    import config


# =============================================================================
# CONFIGURACIÓN
# =============================================================================

class LLMProviderType(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"
    MOCK = "mock"
    DISABLED = "disabled"


@dataclass(frozen=True)
class LLMConfig:
    provider: LLMProviderType = LLMProviderType.MOCK
    api_key: str = ""
    base_url: str = ""
    operator_model: str = "gpt-4o-mini"
    analyst_model: str = "gpt-4o"
    temperature: float = 0.0
    seed: int = 42
    max_tokens: int = 500
    timeout_seconds: float = 3.0
    max_retries: int = 2
    enabled: bool = True

    @classmethod
    def from_env(cls) -> "LLMConfig":
        provider_str = os.getenv("LLM_PROVIDER", "mock").lower()
        try:
            provider = LLMProviderType(provider_str)
        except ValueError:
            provider = LLMProviderType.MOCK

        return cls(
            provider=provider,
            api_key=os.getenv("LLM_API_KEY", ""),
            base_url=os.getenv("LLM_BASE_URL", ""),
            operator_model=os.getenv("LLM_OPERATOR_MODEL", "gpt-4o-mini"),
            analyst_model=os.getenv("LLM_ANALYST_MODEL", "gpt-4o"),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.0")),
            seed=int(os.getenv("LLM_SEED", "42")),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "500")),
            timeout_seconds=float(os.getenv("LLM_TIMEOUT_S", "3.0")),
            max_retries=int(os.getenv("LLM_MAX_RETRIES", "2")),
            enabled=provider != LLMProviderType.DISABLED,
        )

    def is_available(self) -> bool:
        return self.enabled and self.provider != LLMProviderType.DISABLED


# =============================================================================
# ESQUEMAS DE HERRAMIENTAS (FUNCTION CALLING)
# =============================================================================

# Herramientas del Operador de Seguridad (jugador)
OPERATOR_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_player_status",
            "description": "Estado actual del jugador: energía, tarjetas, posición, paso timer",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_argos_status",
            "description": "Estado de ARGOS si es visible: posición, estado, distancia",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_map_info",
            "description": "Información general del mapa: tamaño, objetivos conocidos",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_nearest_terminal",
            "description": "Terminal más cercana sin usar y su distancia",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_action",
            "description": "Sugerir acción validada al jugador",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["move", "hack", "wait", "autopilot"]},
                    "direction": {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2},
                    "reason": {"type": "string"},
                },
                "required": ["action", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reveal_lore",
            "description": "Revelar fragmento de lore/narrativa contextual",
            "parameters": {
                "type": "object",
                "properties": {
                    "fragment_id": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["fragment_id", "text"],
            },
        },
    },
]

# Herramientas del Analista Táctico (ARGOS)
ANALYST_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_full_map",
            "description": "Mapa completo con todos los elementos (omnisciencia)",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_heatmap",
            "description": "Mapa de calor de avistamientos y cruces memorizados",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_all_agents",
            "description": "Estado completo de todos los agentes",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_blockade",
            "description": "Proponer puerta a bloquear con justificación táctica",
            "parameters": {
                "type": "object",
                "properties": {
                    "door": {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2},
                    "rationale": {"type": "string"},
                    "cost_increase": {"type": "number"},
                },
                "required": ["door", "rationale", "cost_increase"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_drone_formation",
            "description": "Coordinar formación de drones",
            "parameters": {
                "type": "object",
                "properties": {
                    "formation": {"type": "string", "enum": ["pincer", "sweep", "ambush", "patrol"]},
                    "drone1_waypoint": {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2},
                    "drone2_waypoint": {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2},
                    "rationale": {"type": "string"},
                },
                "required": ["formation", "rationale"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_player_pattern",
            "description": "Analizar patrón histórico del jugador actual",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern_type": {"type": "string", "enum": ["route_preference", "risk_aversion", "terminal_usage", "card_order"]},
                    "confidence": {"type": "number"},
                    "details": {"type": "string"},
                },
                "required": ["pattern_type", "confidence", "details"],
            },
        },
    },
]


# =============================================================================
# PROVEEDORES LLM
# =============================================================================

@dataclass
class LLMResponse:
    content: str
    tool_calls: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    latency_ms: float = 0.0
    raw: dict = field(default_factory=dict)
    error: str | None = None


class LLMProvider(ABC):
    """Interfaz base para proveedores LLM."""

    def __init__(self, config: LLMConfig):
        self.config = config

    @abstractmethod
    def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str | None = None,
        **kwargs,
    ) -> LLMResponse:
        pass

    @abstractmethod
    async def acomplete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str | None = None,
        **kwargs,
    ) -> LLMResponse:
        pass


class MockProvider(LLMProvider):
    """Proveedor determinista para tests y modo offline."""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self.call_count = 0
        self.operator_responses = [
            {"content": "Operador: Sistemas nominales. Energía estable. Objetivo: sector 4.", "tool_calls": []},
            {"content": "Operador: Terminal detectada en (12,5). Recomiendo hackeo para desactivar sensores.", "tool_calls": [
                {"name": "suggest_action", "arguments": {"action": "hack", "reason": "Desactivar sensores 12s y revelar ARGOS"}}
            ]},
            {"content": "Operador: ¡ALERTA! ARGOS a 3 baldosas. Evita corredor principal. Usa conducto lateral.", "tool_calls": [
                {"name": "suggest_action", "arguments": {"action": "move", "direction": [1, 0], "reason": "Huida lateral"}}
            ]},
            {"content": "Operador: Tarjeta recuperada. Quedan 2. Señales en sectores 7 y 9.", "tool_calls": []},
        ]
        self.analyst_responses = [
            {"content": "Analista: Bloqueo recomendado en puerta (15,8). Corta ruta principal a salida.", "tool_calls": [
                {"name": "suggest_blockade", "arguments": {"door": [15, 8], "rationale": "Corta única ruta viable a salida; alternativa +120 coste", "cost_increase": 120}}
            ]},
            {"content": "Analista: Formación pinza. Dron-1 norte, Dron-2 sur. Interceptan en cruce (12,8).", "tool_calls": [
                {"name": "suggest_drone_formation", "arguments": {"formation": "pincer", "drone1_waypoint": [12, 6], "drone2_waypoint": [12, 10], "rationale": "Ícaro tiende a cruce central; pinza cubre ambas salidas"}}
            ]},
            {"content": "Analista: Patrón detectado: jugador evita sensores 80% partidas. Sesgar predicción a ruta larga.", "tool_calls": [
                {"name": "analyze_player_pattern", "arguments": {"pattern_type": "risk_aversion", "confidence": 0.8, "details": "Historial 5 partidas: ruta segura preferida"}}
            ]},
        ]

    def _next_response(self, is_operator: bool) -> LLMResponse:
        self.call_count += 1
        responses = self.operator_responses if is_operator else self.analyst_responses
        resp = responses[(self.call_count - 1) % len(responses)]
        return LLMResponse(
            content=resp["content"],
            tool_calls=resp.get("tool_calls", []),
            usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            latency_ms=10.0,
            raw=resp,
        )

    def complete(self, messages, tools=None, model=None, **kwargs) -> LLMResponse:
        is_operator = any("OPERADOR" in m.get("content", "") for m in messages if m.get("role") == "system")
        return self._next_response(is_operator)

    async def acomplete(self, messages, tools=None, model=None, **kwargs) -> LLMResponse:
        await asyncio.sleep(0.01)  # Simular latencia mínima
        return self.complete(messages, tools, model, **kwargs)


class OpenAIProvider(LLMProvider):
    """Proveedor OpenAI (GPT-4o, GPT-4o-mini, etc.)."""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._client = None
        self._async_client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(
                    api_key=self.config.api_key,
                    base_url=self.config.base_url or None,
                )
            except ImportError:
                raise RuntimeError("openai package not installed. Run: pip install openai")
        return self._client

    def _get_async_client(self):
        if self._async_client is None:
            try:
                from openai import AsyncOpenAI
                self._async_client = AsyncOpenAI(
                    api_key=self.config.api_key,
                    base_url=self.config.base_url or None,
                )
            except ImportError:
                raise RuntimeError("openai package not installed. Run: pip install openai")
        return self._async_client

    def _call_api(self, client, messages, tools, model, stream=False):
        start = time.perf_counter()
        response = client.chat.completions.create(
            model=model or self.config.operator_model,
            messages=messages,
            tools=tools,
            tool_choice="auto" if tools else "none",
            temperature=self.config.temperature,
            seed=self.config.seed,
            max_tokens=self.config.max_tokens,
            stream=stream,
        )
        latency = (time.perf_counter() - start) * 1000
        return response, latency

    def complete(self, messages, tools=None, model=None, **kwargs) -> LLMResponse:
        try:
            client = self._get_client()
            response, latency = self._call_api(client, messages, tools, model)
            msg = response.choices[0].message
            tool_calls = []
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_calls.append({
                        "name": tc.function.name,
                        "arguments": json.loads(tc.function.arguments),
                    })
            return LLMResponse(
                content=msg.content or "",
                tool_calls=tool_calls,
                usage=response.usage.model_dump() if response.usage else {},
                latency_ms=latency,
                raw=response.model_dump(),
            )
        except Exception as e:
            return LLMResponse(content="", error=str(e))

    async def acomplete(self, messages, tools=None, model=None, **kwargs) -> LLMResponse:
        try:
            client = self._get_async_client()
            response, latency = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self._call_api(client, messages, tools, model)
            )
            msg = response.choices[0].message
            tool_calls = []
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_calls.append({
                        "name": tc.function.name,
                        "arguments": json.loads(tc.function.arguments),
                    })
            return LLMResponse(
                content=msg.content or "",
                tool_calls=tool_calls,
                usage=response.usage.model_dump() if response.usage else {},
                latency_ms=latency,
                raw=response.model_dump(),
            )
        except Exception as e:
            return LLMResponse(content="", error=str(e))


class AnthropicProvider(LLMProvider):
    """Proveedor Anthropic (Claude 3.5 Sonnet, Haiku, etc.)."""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._client = None
        self._async_client = None

    def _get_client(self):
        if self._client is None:
            try:
                from anthropic import Anthropic
                self._client = Anthropic(api_key=self.config.api_key, base_url=self.config.base_url or None)
            except ImportError:
                raise RuntimeError("anthropic package not installed. Run: pip install anthropic")
        return self._client

    def _get_async_client(self):
        if self._async_client is None:
            try:
                from anthropic import AsyncAnthropic
                self._async_client = AsyncAnthropic(api_key=self.config.api_key, base_url=self.config.base_url or None)
            except ImportError:
                raise RuntimeError("anthropic package not installed. Run: pip install anthropic")
        return self._async_client

    def _convert_tools(self, tools: list[dict] | None) -> list[dict] | None:
        if not tools:
            return None
        converted = []
        for t in tools:
            if t.get("type") == "function":
                f = t["function"]
                converted.append({
                    "name": f["name"],
                    "description": f.get("description", ""),
                    "input_schema": f.get("parameters", {"type": "object", "properties": {}}),
                })
        return converted

    def complete(self, messages, tools=None, model=None, **kwargs) -> LLMResponse:
        try:
            client = self._get_client()
            anthropic_tools = self._convert_tools(tools)
            system_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
            user_messages = [m for m in messages if m["role"] != "system"]

            start = time.perf_counter()
            response = client.messages.create(
                model=model or self.config.analyst_model,
                system=system_msg,
                messages=user_messages,
                tools=anthropic_tools,
                tool_choice={"type": "auto"} if anthropic_tools else None,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )
            latency = (time.perf_counter() - start) * 1000

            content = ""
            tool_calls = []
            for block in response.content:
                if block.type == "text":
                    content += block.text
                elif block.type == "tool_use":
                    tool_calls.append({"name": block.name, "arguments": block.input})

            return LLMResponse(
                content=content,
                tool_calls=tool_calls,
                usage={"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens},
                latency_ms=latency,
                raw=response.model_dump(),
            )
        except Exception as e:
            return LLMResponse(content="", error=str(e))

    async def acomplete(self, messages, tools=None, model=None, **kwargs) -> LLMResponse:
        try:
            client = self._get_async_client()
            anthropic_tools = self._convert_tools(tools)
            system_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
            user_messages = [m for m in messages if m["role"] != "system"]

            start = time.perf_counter()
            response = await client.messages.create(
                model=model or self.config.analyst_model,
                system=system_msg,
                messages=user_messages,
                tools=anthropic_tools,
                tool_choice={"type": "auto"} if anthropic_tools else None,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )
            latency = (time.perf_counter() - start) * 1000

            content = ""
            tool_calls = []
            for block in response.content:
                if block.type == "text":
                    content += block.text
                elif block.type == "tool_use":
                    tool_calls.append({"name": block.name, "arguments": block.input})

            return LLMResponse(
                content=content,
                tool_calls=tool_calls,
                usage={"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens},
                latency_ms=latency,
                raw=response.model_dump(),
            )
        except Exception as e:
            return LLMResponse(content="", error=str(e))


class OllamaProvider(LLMProvider):
    """Proveedor Ollama (modelos locales: Llama 3, Qwen, etc.)."""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self.base_url = config.base_url or "http://localhost:11434"

    def complete(self, messages, tools=None, model=None, **kwargs) -> LLMResponse:
        try:
            import requests
            # Ollama no nativamente soporta tools; usar prompt engineering
            prompt = self._build_prompt(messages, tools)
            start = time.perf_counter()
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": model or self.config.operator_model,
                    "prompt": prompt,
                    "temperature": self.config.temperature,
                    "seed": self.config.seed,
                    "options": {"num_predict": self.config.max_tokens},
                    "stream": False,
                },
                timeout=self.config.timeout_seconds,
            )
            latency = (time.perf_counter() - start) * 1000
            data = response.json()
            content = data.get("response", "")
            tool_calls = self._parse_tool_calls(content)
            return LLMResponse(
                content=content,
                tool_calls=tool_calls,
                usage={},  # Ollama no devuelve tokens facilmente
                latency_ms=latency,
                raw=data,
            )
        except Exception as e:
            return LLMResponse(content="", error=str(e))

    async def acomplete(self, messages, tools=None, model=None, **kwargs) -> LLMResponse:
        # Ollama async requiere aiohttp; fallback a sync por simplicidad
        return self.complete(messages, tools, model, **kwargs)

    def _build_prompt(self, messages, tools) -> str:
        parts = []
        for m in messages:
            role = m["role"]
            content = m["content"]
            if role == "system":
                parts.append(f"SYSTEM: {content}")
            elif role == "user":
                parts.append(f"USER: {content}")
            elif role == "assistant":
                parts.append(f"ASSISTANT: {content}")
        if tools:
            parts.append("TOOLS: " + json.dumps(tools, ensure_ascii=False))
            parts.append("Responde en formato JSON con 'tool_calls' si usas herramientas.")
        return "\n\n".join(parts)

    def _parse_tool_calls(self, content: str) -> list[dict]:
        # Intentar extraer JSON de tool_calls del contenido
        try:
            import re
            match = re.search(r'\{.*"tool_calls".*\}', content, re.DOTALL)
            if match:
                data = json.loads(match.group())
                return data.get("tool_calls", [])
        except Exception:
            pass
        return []


def create_provider(config: LLMConfig) -> LLMProvider:
    """Factory para crear proveedor según configuración."""
    if config.provider == LLMProviderType.OPENAI:
        return OpenAIProvider(config)
    elif config.provider == LLMProviderType.ANTHROPIC:
        return AnthropicProvider(config)
    elif config.provider == LLMProviderType.OLLAMA:
        return OllamaProvider(config)
    else:
        return MockProvider(config)


# =============================================================================
# VALIDACIÓN DE ACCIONES
# =============================================================================

class LLMActionValidator:
    """Valida tool_calls del LLM contra reglas del juego."""

    def __init__(self, game: "Game"):
        self.game = game

    # ---- Operador (jugador) ----
    def validate_operator_action(self, tool_call: dict) -> tuple[bool, str, dict | None]:
        name = tool_call.get("name")
        args = tool_call.get("arguments", {})

        if name == "suggest_action":
            action = args.get("action")
            direction = args.get("direction")
            reason = args.get("reason", "")

            if action == "move":
                if not direction or len(direction) != 2:
                    return False, "direction required for move", None
                dx, dy = direction
                if abs(dx) + abs(dy) != 1:
                    return False, "invalid direction (must be orthogonal)", None
                player = self.game.player
                target = (player.tile[0] + dx, player.tile[1] + dy)
                if not self.game.maze.can_enter(target):
                    return False, f"target {target} not enterable", None
                if player.step_timer > 0:
                    return False, "player step cooldown active", None
                return True, "valid move", {"action": "move", "direction": (dx, dy), "reason": reason}

            elif action == "hack":
                terminal = self.game.nearest_terminal()
                if terminal is None:
                    return False, "no terminal in range", None
                if self.game.player.energy <= config.TERMINAL_ENERGY_COST:
                    return False, "insufficient energy", None
                return True, "valid hack", {"action": "hack", "reason": reason}

            elif action == "wait":
                return True, "valid wait", {"action": "wait", "reason": reason}

            elif action == "autopilot":
                return True, "valid autopilot toggle", {"action": "autopilot", "reason": reason}

            return False, f"unknown action: {action}", None

        elif name == "reveal_lore":
            # Siempre válido (solo narrativa)
            return True, "valid lore", {"fragment_id": args.get("fragment_id"), "text": args.get("text")}

        return False, f"unknown tool: {name}", None

    # ---- Analista (ARGOS) ----
    def validate_analyst_action(self, tool_call: dict) -> tuple[bool, str, dict | None]:
        name = tool_call.get("name")
        args = tool_call.get("arguments", {})

        if name == "suggest_blockade":
            door = tuple(args.get("door", []))
            rationale = args.get("rationale", "")

            if len(door) != 2:
                return False, "door must be [x, y]", None
            if self.game.time < self.game.argos.lock_ready_at:
                return False, "blockade cooldown active", None
            if self.game.security < 12.0:
                return False, "insufficient security level", None

            preview = self.game.preview_blockade(door)
            if preview is None:
                return False, "door has no valid more expensive alternative", None
            return True, "valid blockade", {
                "door": door,
                "rationale": rationale,
                "cost_increase": preview["after"] - preview["before"],
            }

        elif name == "suggest_drone_formation":
            formation = args.get("formation")
            wp1 = tuple(args.get("drone1_waypoint", []))
            wp2 = tuple(args.get("drone2_waypoint", []))
            rationale = args.get("rationale", "")

            if formation not in ("pincer", "sweep", "ambush", "patrol"):
                return False, f"invalid formation: {formation}", None
            # Validar waypoints son transitables
            for wp in (wp1, wp2):
                if wp and not self.game.maze.can_enter(wp):
                    return False, f"waypoint {wp} not enterable", None
            return True, "valid formation", {
                "formation": formation,
                "drone1_waypoint": wp1 if wp1 else None,
                "drone2_waypoint": wp2 if wp2 else None,
                "rationale": rationale,
            }

        elif name == "analyze_player_pattern":
            # Siempre válido (solo análisis)
            return True, "valid pattern analysis", args

        return False, f"unknown tool: {name}", None


# =============================================================================
# CACHÉ DE RESPUESTAS (Determinismo)
# =============================================================================

class LLMCache:
    """Caché simple basado en hash de mensajes + tools."""

    def __init__(self, max_size: int = 100):
        self._cache: dict[str, LLMResponse] = {}
        self._max_size = max_size

    def _make_key(self, messages: list[dict], tools: list[dict] | None, model: str) -> str:
        content = json.dumps({
            "messages": messages,
            "tools": tools,
            "model": model,
        }, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(content.encode()).hexdigest()[:32]

    def get(self, messages: list[dict], tools: list[dict] | None, model: str) -> LLMResponse | None:
        key = self._make_key(messages, tools, model)
        return self._cache.get(key)

    def set(self, messages: list[dict], tools: list[dict] | None, model: str, response: LLMResponse) -> None:
        if len(self._cache) >= self._max_size:
            # Eliminar entrada más antigua (simple FIFO)
            oldest = next(iter(self._cache))
            del self._cache[oldest]
        key = self._make_key(messages, tools, model)
        self._cache[key] = response


# =============================================================================
# AGENTES BASE
# =============================================================================

class LLMAgentBase:
    """Base para agentes LLM con ejecución async, timeout, retry, cache."""

    def __init__(self, config: LLMConfig, system_prompt: str, tools: list[dict], model: str):
        self.config = config
        self.system_prompt = system_prompt
        self.tools = tools
        self.model = model
        self.provider = create_provider(config)
        self.cache = LLMCache()
        self.history: list[dict] = []  # Conversación completa
        self.last_call_time = 0.0
        self.last_response: LLMResponse | None = None
        self.pending_task: asyncio.Task | None = None
        self.ready_flag = True

    def _build_messages(self, context: str) -> list[dict]:
        msgs = [{"role": "system", "content": self.system_prompt}]
        if context:
            msgs.append({"role": "user", "content": context})
        return msgs

    def _execute_with_retry(self, messages: list[dict]) -> LLMResponse:
        last_error = None
        for attempt in range(self.config.max_retries + 1):
            # Verificar caché
            cached = self.cache.get(messages, self.tools, self.model)
            if cached:
                cached = LLMResponse(
                    content=cached.content,
                    tool_calls=cached.tool_calls,
                    usage=cached.usage,
                    latency_ms=cached.latency_ms,
                    raw=cached.raw,
                )
                return cached

            response = self.provider.complete(messages, self.tools, self.model)
            if response.error is None:
                self.cache.set(messages, self.tools, self.model, response)
                return response
            last_error = response.error
            if attempt < self.config.max_retries:
                time.sleep(0.1 * (attempt + 1))
        return LLMResponse(content="", error=f"Max retries exceeded: {last_error}")

    async def _execute_async(self, messages: list[dict]) -> LLMResponse:
        last_error = None
        for attempt in range(self.config.max_retries + 1):
            cached = self.cache.get(messages, self.tools, self.model)
            if cached:
                return LLMResponse(
                    content=cached.content,
                    tool_calls=cached.tool_calls,
                    usage=cached.usage,
                    latency_ms=cached.latency_ms,
                    raw=cached.raw,
                )
            try:
                response = await asyncio.wait_for(
                    self.provider.acomplete(messages, self.tools, self.model),
                    timeout=self.config.timeout_seconds,
                )
                if response.error is None:
                    self.cache.set(messages, self.tools, self.model, response)
                    return response
                last_error = response.error
            except asyncio.TimeoutError:
                last_error = f"Timeout after {self.config.timeout_seconds}s"
            except Exception as e:
                last_error = str(e)
            if attempt < self.config.max_retries:
                await asyncio.sleep(0.1 * (attempt + 1))
        return LLMResponse(content="", error=f"Max retries exceeded: {last_error}")

    def think_sync(self, context: str) -> LLMResponse:
        """Ejecución síncrona (bloqueante) - solo para tests/debug."""
        messages = self._build_messages(context)
        response = self._execute_with_retry(messages)
        self._update_history(messages, response)
        return response

    async def think_async(self, context: str) -> LLMResponse:
        """Ejecución asíncrona - no bloquea el bucle principal."""
        messages = self._build_messages(context)
        response = await self._execute_async(messages)
        self._update_history(messages, response)
        return response

    def start_async_think(self, context: str) -> asyncio.Task:
        """Inicia think en background, retorna Task. Usar en Game.update()."""
        if self.pending_task and not self.pending_task.done():
            return self.pending_task
        self.ready_flag = False
        self.pending_task = asyncio.create_task(self.think_async(context))
        return self.pending_task

    def check_ready(self) -> tuple[bool, LLMResponse | None]:
        """Verifica si la task async terminó. Retorna (ready, response)."""
        if self.pending_task and self.pending_task.done():
            try:
                response = self.pending_task.result()
                self.ready_flag = True
                self.last_response = response
                return True, response
            except Exception as e:
                self.ready_flag = True
                err_resp = LLMResponse(content="", error=str(e))
                self.last_response = err_resp
                return True, err_resp
        return self.ready_flag, self.last_response

    def _update_history(self, messages: list[dict], response: LLMResponse):
        self.history.extend(messages[1:])  # Skip system prompt duplicate
        if response.content:
            self.history.append({"role": "assistant", "content": response.content})
        if response.tool_calls:
            for tc in response.tool_calls:
                self.history.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{"id": f"call_{hash(str(tc))}", "type": "function", "function": tc}],
                })
        # Limitar historial
        if len(self.history) > 20:
            self.history = self.history[-20:]


# =============================================================================
# AGENTE 1: OPERADOR DE SEGURIDAD
# =============================================================================

OPERATOR_SYSTEM_PROMPT = """Eres el OPERADOR DE SEGURIDAD de la Estación Subterránea 07.
Tu interfaz está conectada al traje de supervivencia de Ícaro. Tu misión: guiarle a la salida.

REGLAS ESTRICTAS:
- Solo puedes OBSERVAR y SUGERIR. No controlas el traje directamente.
- Tus sugerencias deben ser ACCIONABLES y SEGURAS (el sistema las valida).
- Adapta tu tono: urgente si ARGOS cerca, calmado si explorando.
- Revela lore progresivamente: logs, grabaciones, estado de la estación.
- NUNCA reveles información que el jugador no podría saber (respeta niebla de guerra).
- Sé conciso: máx 2 frases por respuesta.

HERRAMIENTAS DISPONIBLES:
- get_player_status: energía, tarjetas, posición
- get_argos_status: estado ARGOS si visible
- get_map_info: objetivos conocidos
- get_nearest_terminal: terminal más cercana
- suggest_action: mover, hackear, esperar, autopiloto
- reveal_lore: fragmento narrativo

FORMATO RESPUESTA:
Siempre incluye diálogo en 'content'. Usa tools para sugerencias accionables."""


class OperatorAgent(LLMAgentBase):
    """Agente conversacional para el jugador."""

    def __init__(self, config: LLMConfig):
        super().__init__(config, OPERATOR_SYSTEM_PROMPT, OPERATOR_TOOLS, config.operator_model)
        self.personality_seed = 0
        self.personality_traits = {}
        self.conversation_count = 0

    def set_game_seed(self, seed: int):
        self.personality_seed = seed
        rng = __import__("random").Random(self.personality_seed)
        self.personality_traits = {
            "tone": rng.choice(["militar", "calmado", "sarcastico", "tecnico"]),
            "verbosity": rng.choice(["conciso", "detallado"]),
            "risk_tolerance": rng.choice(["conservador", "agresivo"]),
        }

    def build_context(self, game: "Game", trigger: str = "manual") -> str:
        """Construye contexto inyectado al prompt."""
        player = game.player
        argos = game.argos

        ctx = {
            "trigger": trigger,
            "time": f"{game.time:.1f}s",
            "player": {
                "energy": round(player.energy, 1),
                "cards": len(player.cards),
                "max_cards": config.CARD_COUNT,
                "position": player.tile,
                "step_timer": round(player.step_timer, 2),
            },
            "objectives": {
                "remaining_cards": len(game.remaining_cards),
                "exit_active": game.exit_active,
                "exit_position": game.maze.exit if game.exit_active or len(player.cards) > 0 else "unknown",
            },
            "argos": {
                "visible": argos.player_visible,
                "state": argos.state,
                "position": argos.tile if argos.player_visible or game.reveal_active else "unknown",
                "distance": abs(argos.tile[0] - player.tile[0]) + abs(argos.tile[1] - player.tile[1]) if argos.player_visible else "unknown",
            },
            "security": round(game.security, 1),
            "sensors_active": game.sensors_active,
            "terminals_available": len([t for t in game.maze.terminals if t not in game.used_terminals]),
            "personality": self.personality_traits,
        }
        return json.dumps(ctx, ensure_ascii=False)

    def process_response(self, game: "Game", response: LLMResponse, validator: LLMActionValidator) -> list[dict]:
        """Procesa respuesta: valida tools, ejecuta acciones válidas, retorna eventos para log/UI."""
        events = []

        # Diálogo siempre se muestra
        if response.content:
            events.append({"type": "dialogue", "speaker": "OPERADOR", "text": response.content})

        # Validar y ejecutar tool_calls
        for tc in response.tool_calls:
            valid, msg, validated_args = validator.validate_operator_action(tc)
            if valid:
                events.append({"type": "tool_validated", "tool": tc["name"], "args": validated_args})
                self._execute_operator_action(game, validated_args, events)
            else:
                events.append({"type": "tool_rejected", "tool": tc["name"], "reason": msg})
                # Log para debugging
                game.log_event("OPERADOR", f"Tool rechazada: {tc['name']} - {msg}", "sistema")

        self.conversation_count += 1
        return events

    def _execute_operator_action(self, game: "Game", action: dict, events: list):
        act = action.get("action")
        if act == "move":
            game.attempt_player_move(action["direction"])
            events.append({"type": "action_executed", "action": "move", "direction": action["direction"]})
        elif act == "hack":
            game.hack_terminal()
            events.append({"type": "action_executed", "action": "hack"})
        elif act == "autopilot":
            game.toggle_autopilot()
            events.append({"type": "action_executed", "action": "autopilot"})
        # wait no requiere ejecución

    def get_recent_dialogue(self, n: int = 3) -> list[str]:
        """Últimos n diálogos para historial en panel."""
        dialogues = [e for e in reversed(self.history) if e.get("role") == "assistant" and e.get("content")]
        return [d["content"] for d in dialogues[:n]]


# =============================================================================
# AGENTE 2: ANALISTA TÁCTICO
# =============================================================================

ANALYST_SYSTEM_PROMPT = """Eres el ANALISTA TÁCTICO del sistema ARGOS.
Tienes acceso completo a sensores, mapas de calor, historial de partidas y estado actual.
Tu salida: DECISIONES TÁCTICAS VALIDADAS para ARGOS y drones.

OBJETIVO: Maximizar probabilidad de captura de Ícaro minimizando recursos.

RESTRICCIONES:
- Sugerencias deben ser EJECUTABLES en el turno actual (cooldowns, alcance, reglas).
- Prioriza: 1) Bloqueo corredor crítico 2) Formación drones 3) Intercepción predicción
- Explica tu razonamiento en 'rationale' para logging/auditoría.
- Sé preciso: coordenadas exactas, valores numéricos.

HERRAMIENTAS DISPONIBLES:
- get_full_map: mapa completo (omnisciencia)
- get_heatmap: mapa de calor avistamientos/cruces
- get_all_agents: estado todos los agentes
- suggest_blockade: proponer puerta a bloquear + justificación + coste extra
- suggest_drone_formation: coordinar drones (pinza, barrido, emboscada, patrulla)
- analyze_player_pattern: analizar patrón histórico

FORMATO RESPUESTA:
JSON con tool_calls. Incluye 'rationale' explicativo en cada herramienta."""


class AnalystAgent(LLMAgentBase):
    """Agente asesor estratégico para ARGOS."""

    def __init__(self, config: LLMConfig):
        super().__init__(config, ANALYST_SYSTEM_PROMPT, ANALYST_TOOLS, config.analyst_model)
        self.last_suggestion_time = -999.0
        self.suggestion_cooldown = 2.0  # Segundos entre sugerencias
        self.cached_suggestions: dict = {}

    def build_context(self, game: "Game") -> str:
        """Estado completo (omnisciencia) para el analista."""
        argos = game.argos
        player = game.player
        maze = game.maze

        ctx = {
            "time": round(game.time, 1),
            "security": round(game.security, 1),
            "argos": {
                "position": argos.tile,
                "state": argos.state,
                "target": argos.target_label,
                "path_len": len(argos.path),
                "goal": argos.goal,
                "prediction": {
                    "target": argos.prediction.target if argos.prediction else None,
                    "probable": argos.prediction.probable if argos.prediction else None,
                    "rationale": argos.prediction.rationale if argos.prediction else None,
                } if argos.prediction else None,
                "player_visible": argos.player_visible,
                "last_seen": argos.last_seen,
                "lock_ready_in": max(0, argos.lock_ready_at - game.time),
                "heat_top5": dict(argos.heat.most_common(5)),
                "crossings": list(argos.crossings),
            },
            "player": {
                "position": player.tile,
                "energy": round(player.energy, 1),
                "cards": len(player.cards),
                "objectives": [list(game.remaining_cards), game.maze.exit] if game.remaining_cards else [game.maze.exit],
                "autopilot": game.autopilot,
            },
            "drones": [
                {
                    "name": d.name,
                    "position": d.tile,
                    "state": d.state,
                    "waypoint": d.route[d.route_index % len(d.route)] if d.route else None,
                    "last_report": round(game.time - d.last_report_at, 1) if d.last_report_at > -900 else None,
                }
                for d in game.drones
            ],
            "map": {
                "width": maze.width,
                "height": maze.height,
                "doors": list(maze.doors),
                "locked_doors": list(maze.locked_doors.keys()),
                "sensors": list(maze.sensors),
                "terminals": list(maze.terminals),
                "hazards": list(maze.hazards),
                "cards": list(maze.cards),
                "exit": maze.exit,
            },
        }
        return json.dumps(ctx, ensure_ascii=False)

    def should_analyze(self, game: "Game") -> bool:
        """Decide si vale la pena consultar al LLM ahora."""
        now = game.time
        argos = game.argos

        # Cooldown básico
        if now - self.last_suggestion_time < self.suggestion_cooldown:
            return False

        # Triggers de alto valor
        triggers = [
            argos.player_visible and argos.state in ("CAZA", "INTERCEPTA"),
            argos.state == "INVESTIGA" and argos.last_seen is not None,
            game.security >= 50 and argos.lock_ready_at <= now,
            any(d.player_visible for d in game.drones),
            game.autopilot and game.bot.path and game.argos.path,  # Ambos planificando
        ]

        return any(triggers)

    def process_response(self, game: "Game", response: LLMResponse, validator: LLMActionValidator) -> list[dict]:
        """Procesa respuesta del analista: valida, cachea sugerencias, retorna eventos."""
        events = []
        self.last_suggestion_time = game.time

        for tc in response.tool_calls:
            valid, msg, validated_args = validator.validate_analyst_action(tc)
            if valid:
                events.append({"type": "analyst_suggestion", "tool": tc["name"], "args": validated_args})
                self.cached_suggestions[tc["name"]] = validated_args
            else:
                events.append({"type": "analyst_rejected", "tool": tc["name"], "reason": msg})
                game.log_event("ANALISTA", f"Sugerencia rechazada: {tc['name']} - {msg}", "sistema")

        return events

    def get_cached_suggestion(self, tool_name: str) -> dict | None:
        return self.cached_suggestions.get(tool_name)

    def clear_cache(self):
        self.cached_suggestions.clear()


# =============================================================================
# INTEGRACIÓN EN GAME (helpers)
# =============================================================================

def initialize_llm_agents(config: LLMConfig) -> tuple["OperatorAgent | None", "AnalystAgent | None"]:
    """Crea agentes LLM si configuración habilitada."""
    if not config.is_available():
        return None, None
    try:
        operator = OperatorAgent(config)
        analyst = AnalystAgent(config)
        return operator, analyst
    except Exception as e:
        print(f"[LLM] Error inicializando agentes: {e}")
        return None, None


async def run_llm_turn(game: "Game", operator: "OperatorAgent | None", analyst: "AnalystAgent | None"):
    """Ejecuta un turno de agentes LLM (llamado desde Game.update o task async)."""
    if not operator and not analyst:
        return

    validator = LLMActionValidator(game)
    events = []

    # Operador: solo si jugador lo invoca (tecla H) o evento automático
    # (La invocación manual se maneja en App._handle_key)

    # Analista: si ARGOS necesita decisión compleja
    if analyst and analyst.should_analyze(game):
        try:
            context = analyst.build_context(game)
            response = await analyst.think_async(context)
            if response.error:
                game.log_event("ANALISTA", f"Error LLM: {response.error}", "error")
            else:
                events.extend(analyst.process_response(game, response, validator))
        except Exception as e:
            game.log_event("ANALISTA", f"Excepción: {e}", "error")

    # Log eventos LLM
    for ev in events:
        if ev["type"] in ("dialogue", "analyst_suggestion"):
            game.log_event(ev.get("speaker", "LLM"), ev.get("text", str(ev)), "llm")


# =============================================================================
# TESTS RÁPIDOS
# =============================================================================

if __name__ == "__main__":
    import asyncio

    async def test_mock():
        cfg = LLMConfig(provider=LLMProviderType.MOCK, enabled=True)
        op, an = initialize_llm_agents(cfg)

        # Test Operator
        if op:
            print("=== OPERADOR TEST ===")
            op.set_game_seed(7)
            resp = op.think_sync("Test context")
            print(f"Content: {resp.content}")
            print(f"Tools: {resp.tool_calls}")
            print(f"Latency: {resp.latency_ms:.1f}ms")

        # Test Analyst
        if an:
            print("\n=== ANALISTA TEST ===")
            resp = an.think_sync("Test context")
            print(f"Content: {resp.content}")
            print(f"Tools: {resp.tool_calls}")

        # Test Async
        print("\n=== ASYNC TEST ===")
        if op:
            task = op.start_async_think("Async test")
            await asyncio.sleep(0.1)
            ready, resp = op.check_ready()
            print(f"Ready: {ready}, Content: {resp.content if resp else None}")

    asyncio.run(test_mock())
    print("\n✅ Tests básicos pasados")