"""Constantes de configuración del juego.

Todo el ajuste fino (velocidades, costes, energía, tiempos de bloqueo) vive
aquí para poder reproducir escenarios y variar parámetros sin tocar la lógica.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Identidad / ventana
# ---------------------------------------------------------------------------
APP_NAME = "El escape de Ícaro"
APP_SUBTITLE = "Laberinto de supervivencia · IA agéntica"
WINDOW_W = 1400
WINDOW_H = 800
FPS = 60
TIME_LIMIT = 180.0

HUD_H = 64
MAZE_RECT = (16, 70, 930, 690)
PANEL_RECT = (958, 70, 426, 690)
FOOTER_Y = 776

# Tamaño de mapa por defecto (en celdas del generador; las baldosas son 2*n+1)
DEFAULT_CELLS_X = 17
DEFAULT_CELLS_Y = 12
DEFAULT_SEED = 7

# ---------------------------------------------------------------------------
# Grafo / costes de las baldosas
# ---------------------------------------------------------------------------
FLOOR_COST = 1.0
SENSOR_COST = 2.0
HAZARD_COST = 3.0
DOOR_COST = 1.0

# ---------------------------------------------------------------------------
# Jugador
# ---------------------------------------------------------------------------
CARD_COUNT = 3
ENERGY_MAX = 100.0
ENERGY_DRAIN_PER_S = 0.85          # consumo base por estar vivo
HAZARD_ENERGY_PENALTY = 4.0        # coste extra al pisar vapor/riesgo
PLAYER_STEP_TIME = 0.125           # segundos por baldosa
PLAYER_VISION = 7.4                # radio de visión (baldosas)
TERMINAL_ENERGY_COST = 5.0
TERMINAL_RANGE = 1.25

# ---------------------------------------------------------------------------
# ARGOS (cazador)
# ---------------------------------------------------------------------------
ARGOS_STEP_TIME = 0.225
ARGOS_STEP_MIN = 0.176             # con alerta máxima acelera
ARGOS_THINK_TIME = 0.38
ARGOS_VISION = 8.5
ARGOS_MEMORY_TTL = 12.0            # segundos que recuerda la última posición
ARGOS_LOCK_COOLDOWN = 15.0
ARGOS_LOCK_AFTER = 6.0             # primera puerta bloqueable
DOOR_LOCK_TIME = 10.0
PREDICTION_DEPTH = 4
PREDICTION_BUDGET = 700

# ---------------------------------------------------------------------------
# Drones exploradores
# ---------------------------------------------------------------------------
DRONE_STEP_TIME = 0.30
DRONE_THINK_TIME = 0.55
DRONE_VISION = 6.0
DRONE_REPORT_COOLDOWN = 4.0
DRONE_COUNT = 2

# ---------------------------------------------------------------------------
# Seguridad / energía del sistema
# ---------------------------------------------------------------------------
SECURITY_MAX = 100.0
SECURITY_DECAY_PER_S = 1.15
SENSOR_SECURITY = 20.0
DRONE_SECURITY = 6.0
CARD_SECURITY = 10.0
ARGOS_SECURITY_PER_S = 5.0
SENSORS_DISABLED_TIME = 12.0
REVEAL_TIME = 8.0

# ---------------------------------------------------------------------------
# Paleta visual
# ---------------------------------------------------------------------------
COL_BG = (5, 9, 15)
COL_BG_2 = (9, 14, 23)
COL_PANEL = (10, 17, 27)
COL_PANEL_DARK = (7, 12, 19)
COL_PANEL_EDGE = (29, 48, 66)
COL_PANEL_SOFT = (17, 28, 42)

COL_CYAN = (80, 232, 255)
COL_CYAN_DIM = (39, 120, 139)
COL_AMBER = (255, 195, 84)
COL_RED = (255, 78, 101)
COL_RED_DARK = (116, 29, 43)
COL_GREEN = (90, 255, 167)
COL_PURPLE = (185, 124, 255)
COL_BLUE = (112, 160, 255)

COL_TEXT = (224, 237, 247)
COL_MUTED = (126, 151, 173)
COL_DIM = (72, 96, 118)

COL_WALL = (34, 47, 66)
COL_WALL_TOP = (54, 74, 97)
COL_WALL_SHADOW = (20, 30, 44)
COL_FLOOR = (12, 21, 33)
COL_FLOOR_2 = (14, 25, 38)
COL_GRID = (22, 36, 51)

# ---------------------------------------------------------------------------
# Nombres de algoritmos
# ---------------------------------------------------------------------------
ALGO_ASTAR = "astar"
ALGO_DIJKSTRA = "dijkstra"
ALGO_LABEL = {ALGO_ASTAR: "A*", ALGO_DIJKSTRA: "Dijkstra"}

# Teclas mostradas en la documentación / HUD
CONTROLS = [
    ("WASD / flechas", "Mover a Ícaro"),
    ("E", "Hackear terminal cercano"),
    ("P", "Activar/desactivar piloto automático"),
    ("H", "Hablar con Operador (LLM)"),
    ("TAB / 1-4", "Seleccionar agente en el panel"),
    ("F1", "Alternar A* ↔ Dijkstra"),
    ("F2", "Mostrar/ocultar rutas planificadas"),
    ("F3", "Niebla de guerra on/off"),
    ("F5", "Prueba de bloqueo de corredor"),
    ("F6", "Alarma de demostración"),
    ("R", "Reiniciar (misma semilla)"),
    ("N", "Nueva semilla"),
    ("F11", "Pantalla completa"),
    ("ESC", "Pausa / salir"),
]
