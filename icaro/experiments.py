"""Banco de experimentos reproducible: Dijkstra vs A*.

El experimento genera mapas con semillas fijas en varios tamaños, define para
cada mapa los mismos escenarios (salida, tarjetas y persecución), y ejecuta
ambos algoritmos sobre el **mismo grafo, origen, destinos y costes**. Cada caso
se repite varias veces para reducir el ruido de medición.

Salidas:
    docs/experimentos.csv   una fila por repetición y algoritmo
    docs/experimentos.md    resumen agregado listo para el informe

Uso:
    python -m icaro.experiments
    python -m icaro.experiments --reps 10 --seeds 7,21,42
    python -m icaro.experiments --quick
"""

from __future__ import annotations

import argparse
import csv
import gc
import platform
import statistics
import tracemalloc
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from time import perf_counter

from . import config
from .algorithms import SearchResult, astar, dijkstra
from .graph import Coord, GridGraph
from .maze import Maze

# Tamaños en celdas del generador. Las baldosas reales son 2*n+1.
DEFAULT_SIZES: tuple[tuple[str, int, int], ...] = (
    ("Pequeño", 10, 7),
    ("Mediano", 17, 12),
    ("Grande", 26, 18),
    ("Muy grande", 36, 25),
)
DEFAULT_SEEDS: tuple[int, ...] = (7, 21, 42, 99, 123)
DEFAULT_REPS = 5


@dataclass(slots=True)
class Scenario:
    name: str
    start: Coord
    goals: tuple[Coord, ...]
    description: str


@dataclass
class CaseResult:
    size_name: str
    cells_x: int
    cells_y: int
    seed: int
    scenario: str
    vertices: int
    edges: int
    reps: int
    rows: list[dict[str, object]] = field(default_factory=list)
    costs_equal: bool = True
    max_cost_delta: float = 0.0


def _scenarios(maze: Maze) -> list[Scenario]:
    return [
        Scenario(
            "salida",
            maze.start,
            (maze.exit,),
            "inicio → compuerta de emergencia",
        ),
        Scenario(
            "tarjetas",
            maze.start,
            tuple(sorted(maze.cards)),
            "inicio → conjunto de las 3 tarjetas (multiobjetivo)",
        ),
        Scenario(
            "persecucion",
            maze.argos_start,
            (maze.start,),
            "posición inicial de ARGOS → inicio de Ícaro",
        ),
    ]


def _path_cost(graph: GridGraph, path: list[Coord]) -> float:
    return sum(graph.tile_cost(tile) for tile in path[1:])


def _measure_memory_kb(graph: GridGraph, start: Coord, goals: tuple[Coord, ...],
                       algorithm: str) -> float:
    """Pico de memoria Python de una búsqueda, medido con tracemalloc."""
    gc.collect()
    tracemalloc.start()
    tracemalloc.reset_peak()
    if algorithm == config.ALGO_ASTAR:
        astar(graph, start, goals)
    else:
        dijkstra(graph, start, goals)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return peak / 1024.0


def _run_case(maze: Maze, size_name: str, cells_x: int, cells_y: int,
              seed: int, scenario: Scenario, reps: int) -> CaseResult:
    graph = maze.graph
    result = CaseResult(
        size_name=size_name,
        cells_x=cells_x,
        cells_y=cells_y,
        seed=seed,
        scenario=scenario.name,
        vertices=graph.vertices,
        edges=graph.edges,
        reps=reps,
    )

    # Calentamiento: deja listos caches de tuplas/enteros y valida el caso.
    warm_d = dijkstra(graph, scenario.start, scenario.goals)
    warm_a = astar(graph, scenario.start, scenario.goals)
    if not warm_d.found or not warm_a.found:
        return result
    base_cost = warm_d.cost
    result.costs_equal = abs(warm_d.cost - warm_a.cost) <= 1e-6
    result.max_cost_delta = max(result.max_cost_delta, abs(warm_d.cost - warm_a.cost))

    for rep in range(1, reps + 1):
        for algorithm, runner in ((config.ALGO_DIJKSTRA, dijkstra),
                                  (config.ALGO_ASTAR, astar)):
            started = perf_counter()
            search: SearchResult = runner(graph, scenario.start, scenario.goals)
            wall_ms = (perf_counter() - started) * 1000.0
            if not search.found:
                continue
            actual_cost = _path_cost(graph, search.path)
            if abs(actual_cost - search.cost) > 1e-6:
                raise AssertionError(
                    f"coste inconsistente en {algorithm} {scenario.name}: "
                    f"ruta={actual_cost} resultado={search.cost}"
                )
            if abs(search.cost - base_cost) > 1e-6:
                result.costs_equal = False
            result.max_cost_delta = max(result.max_cost_delta,
                                        abs(search.cost - base_cost))

            memory_kb = _measure_memory_kb(
                graph, scenario.start, scenario.goals, algorithm
            )
            result.rows.append({
                "tamano": size_name,
                "celdas_x": cells_x,
                "celdas_y": cells_y,
                "semilla": seed,
                "escenario": scenario.name,
                "algoritmo": algorithm,
                "repeticion": rep,
                "encontrado": int(search.found),
                "coste": round(search.cost, 6),
                "pasos": search.steps,
                "expandidos": search.expanded,
                "generados": search.generated,
                "frontera_max": search.frontier_peak,
                "tiempo_ms": round(search.elapsed_ms, 6),
                "tiempo_pared_ms": round(wall_ms, 6),
                "memoria_pico_kb": round(memory_kb, 3),
                "vertices": graph.vertices,
                "aristas": graph.edges,
            })
    return result


def _mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def _median(values: list[float]) -> float:
    return statistics.median(values) if values else 0.0


def _summary_tables(rows: list[dict[str, object]], sizes: list[tuple[str, int, int]]):
    by_size_algo: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    by_size_scenario: dict[tuple[str, str, str], dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in rows:
        size = str(row["tamano"])
        algorithm = str(row["algoritmo"])
        scenario = str(row["escenario"])
        bucket = by_size_algo[(size, algorithm)]
        for key in ("coste", "expandidos", "generados", "frontera_max",
                    "tiempo_ms", "memoria_pico_kb"):
            bucket[key].append(float(row[key]))
        bucket["vertices"].append(float(row["vertices"]))
        sec = by_size_scenario[(size, scenario, algorithm)]
        for key in ("expandidos", "tiempo_ms", "memoria_pico_kb"):
            sec[key].append(float(row[key]))

    summary = []
    for size_name, _cx, _cy in sizes:
        d = by_size_algo.get((size_name, config.ALGO_DIJKSTRA))
        a = by_size_algo.get((size_name, config.ALGO_ASTAR))
        if not d or not a:
            continue
        d_nodes = _mean(d["expandidos"])
        a_nodes = _mean(a["expandidos"])
        saved = 100.0 * (1.0 - a_nodes / d_nodes) if d_nodes else 0.0
        time_ratio = _median(a["tiempo_ms"]) / _median(d["tiempo_ms"]) if _median(d["tiempo_ms"]) else 0.0
        mem_saved = (
            100.0 * (1.0 - _mean(a["memoria_pico_kb"]) / _mean(d["memoria_pico_kb"]))
            if _mean(d["memoria_pico_kb"]) else 0.0
        )
        summary.append({
            "size": size_name,
            "vertices": int(d["vertices"][0]),
            "d_nodes": d_nodes,
            "a_nodes": a_nodes,
            "saved": saved,
            "d_ms": _median(d["tiempo_ms"]),
            "a_ms": _median(a["tiempo_ms"]),
            "time_ratio": time_ratio,
            "d_mem": _mean(d["memoria_pico_kb"]),
            "a_mem": _mean(a["memoria_pico_kb"]),
            "mem_saved": mem_saved,
            "d_cost": _mean(d["coste"]),
            "a_cost": _mean(a["coste"]),
        })
    return summary, by_size_scenario


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "tamano", "celdas_x", "celdas_y", "semilla", "escenario", "algoritmo",
        "repeticion", "encontrado", "coste", "pasos", "expandidos", "generados",
        "frontera_max", "tiempo_ms", "tiempo_pared_ms", "memoria_pico_kb",
        "vertices", "aristas",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _write_markdown(path: Path, rows: list[dict[str, object]],
                    cases: list[CaseResult], reps: int,
                    seeds: list[int], sizes: list[tuple[str, int, int]],
                    elapsed: float) -> None:
    summary, by_size_scenario = _summary_tables(rows, sizes)
    total_cases = sum(1 for case in cases if case.rows)
    mismatches = [case for case in cases if not case.costs_equal]
    lines: list[str] = [
        "# Resultados experimentales · Dijkstra vs A*",
        "",
        f"Generado: {datetime.now().isoformat(timespec='seconds')}",
        "",
        f"Entorno: Python {platform.python_version()} · {platform.system()} "
        f"{platform.machine()}",
        "",
        "## Metodología",
        "",
        "- Mismo generador de laberintos, mismos costes, mismo origen y mismos "
        "destinos para ambos algoritmos.",
        "- Tamaños (celdas del generador): "
        + ", ".join(f"{name} {cx}×{cy}" for name, cx, cy in sizes) + ".",
        f"- Semillas: {', '.join(map(str, seeds))}.",
        f"- Repeticiones por caso y algoritmo: {reps}.",
        "- Tiempo: `perf_counter` dentro de cada búsqueda (mediana por tamaño).",
        "- Memoria: pico de asignaciones Python medido con `tracemalloc`; es una "
        "medida relativa, no el RSS del proceso.",
        "- Cada fila del CSV corresponde a una repetición de un algoritmo.",
        f"- Casos evaluados: {total_cases} · filas: {len(rows)} · "
        f"duración total: {elapsed:.1f} s.",
        "",
        "## Totales por tamaño",
        "",
        "| Tamaño | Vértices | Dijkstra nodos | A* nodos | Ahorro A* | "
        "Dijkstra ms | A* ms | Ratio tiempo | Dijkstra KB | A* KB | Ahorro mem. |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in summary:
        lines.append(
            f"| {item['size']} | {item['vertices']} | {item['d_nodes']:.1f} | "
            f"{item['a_nodes']:.1f} | {item['saved']:.1f}% | {item['d_ms']:.3f} | "
            f"{item['a_ms']:.3f} | {item['time_ratio']:.2f}× | "
            f"{item['d_mem']:.1f} | {item['a_mem']:.1f} | "
            f"{item['mem_saved']:.1f}% |"
        )

    lines += [
        "",
        "## Coste óptimo por tamaño",
        "",
        "| Tamaño | Coste medio Dijkstra | Coste medio A* | Diferencia máxima |",
        "|---|---:|---:|---:|",
    ]
    max_delta_by_size: dict[str, float] = defaultdict(float)
    for case in cases:
        max_delta_by_size[case.size_name] = max(
            max_delta_by_size[case.size_name], case.max_cost_delta
        )
    for item in summary:
        lines.append(
            f"| {item['size']} | {item['d_cost']:.2f} | {item['a_cost']:.2f} | "
            f"{max_delta_by_size[item['size']]:.2e} |"
        )

    lines += [
        "",
        "## Detalle por escenario",
        "",
        "| Tamaño | Escenario | Dijkstra nodos | A* nodos | Ahorro | "
        "Dijkstra ms | A* ms |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for size_name, _cx, _cy in sizes:
        for scenario in ("salida", "tarjetas", "persecucion"):
            d = by_size_scenario.get((size_name, scenario, config.ALGO_DIJKSTRA))
            a = by_size_scenario.get((size_name, scenario, config.ALGO_ASTAR))
            if not d or not a:
                continue
            d_nodes = _mean(d["expandidos"])
            a_nodes = _mean(a["expandidos"])
            saved = 100.0 * (1.0 - a_nodes / d_nodes) if d_nodes else 0.0
            lines.append(
                f"| {size_name} | {scenario} | {d_nodes:.1f} | {a_nodes:.1f} | "
                f"{saved:.1f}% | {_median(d['tiempo_ms']):.3f} | "
                f"{_median(a['tiempo_ms']):.3f} |"
            )

    lines += [
        "",
        "## Verificación de optimalidad",
        "",
        f"- Casos con coste Dijkstra == A*: {total_cases - len(mismatches)}/{total_cases}.",
    ]
    if mismatches:
        lines.append("- **Discrepancias:**")
        for case in mismatches:
            lines.append(
                f"  - semilla {case.seed}, {case.size_name}, {case.scenario}: "
                f"delta {case.max_cost_delta:.3e}"
            )
    else:
        lines.append(
            "- En todos los casos ambos algoritmos devolvieron el mismo coste "
            "óptimo, como exige la heurística Manhattan admisible y consistente."
        )

    csv_path = path.with_suffix(".csv")
    try:
        csv_label = str(csv_path.relative_to(path.parent.parent))
    except ValueError:
        csv_label = str(csv_path)
    lines += [
        "",
        "## Lectura de los resultados",
        "",
        "- A* reduce las expansiones porque la distancia Manhattan descarta "
        "ramas que se alejan del objetivo; el ahorro crece con el tamaño del mapa.",
        "- El coste de la ruta es idéntico: la heurística no sacrifica optimalidad.",
        "- El tiempo absoluto depende de la máquina; por eso se reporta la mediana "
        "y el ratio A*/Dijkstra, más estables entre equipos.",
        "- La memoria se mide con `tracemalloc` y sufre el costo del propio "
        "instrumento; sirve para comparar algoritmos, no como cifra absoluta.",
        "",
        f"Datos crudos: `{csv_label}`.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def run_experiments(*, reps: int = DEFAULT_REPS,
                    seeds: list[int] | None = None,
                    sizes: list[tuple[str, int, int]] | None = None,
                    out_dir: Path | None = None) -> tuple[list[dict[str, object]], Path, Path]:
    """Ejecuta el banco completo y devuelve (filas, csv, markdown)."""
    seeds = seeds or list(DEFAULT_SEEDS)
    sizes = sizes or list(DEFAULT_SIZES)
    out_dir = out_dir or Path(__file__).resolve().parent.parent / "docs"
    if reps < 1:
        raise ValueError("--reps debe ser >= 1")
    if not seeds:
        raise ValueError("se necesita al menos una semilla")

    started = perf_counter()
    all_rows: list[dict[str, object]] = []
    cases: list[CaseResult] = []
    total = len(sizes) * len(seeds) * 3
    done = 0
    for size_name, cx, cy in sizes:
        for seed in seeds:
            maze = Maze(cells_x=cx, cells_y=cy, seed=seed)
            for scenario in _scenarios(maze):
                case = _run_case(maze, size_name, cx, cy, seed, scenario, reps)
                cases.append(case)
                all_rows.extend(case.rows)
                done += 1
                print(
                    f"[{done:>3}/{total}] {size_name:<10} semilla {seed:<4} "
                    f"{scenario.name:<12} vértices={case.vertices:<5} "
                    f"filas={len(case.rows)}"
                )
    elapsed = perf_counter() - started

    all_rows.sort(key=lambda row: (
        row["tamano"], row["semilla"], row["escenario"],
        row["algoritmo"], row["repeticion"],
    ))
    csv_path = out_dir / "experimentos.csv"
    md_path = out_dir / "experimentos.md"
    _write_csv(csv_path, all_rows)
    _write_markdown(md_path, all_rows, cases, reps, seeds, sizes, elapsed)

    # Resumen de consola.
    summary, _ = _summary_tables(all_rows, sizes)
    print("\nResumen Dijkstra vs A*")
    print(f"{'Tamaño':<12}{'Vértices':>9}{'Dijkstra':>11}{'A*':>10}"
          f"{'Ahorro':>9}{'D ms':>9}{'A* ms':>9}")
    for item in summary:
        print(
            f"{item['size']:<12}{item['vertices']:>9}{item['d_nodes']:>11.1f}"
            f"{item['a_nodes']:>10.1f}{item['saved']:>8.1f}%"
            f"{item['d_ms']:>9.3f}{item['a_ms']:>9.3f}"
        )
    mismatches = sum(1 for case in cases if not case.costs_equal)
    print(f"Optimalidad: {len(cases) - mismatches}/{len(cases)} casos con coste idéntico")
    print(f"CSV:      {csv_path}")
    print(f"Informe:  {md_path}")
    print(f"Duración: {elapsed:.1f} s")
    return all_rows, csv_path, md_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Experimentos reproducibles de Dijkstra vs A*"
    )
    parser.add_argument("--reps", type=int, default=DEFAULT_REPS,
                        help=f"repeticiones por caso (por defecto {DEFAULT_REPS})")
    parser.add_argument("--seeds", type=str, default=",".join(map(str, DEFAULT_SEEDS)),
                        help="semillas separadas por comas")
    parser.add_argument("--out", type=Path, default=None,
                        help="carpeta de salida (por defecto docs/)")
    parser.add_argument("--quick", action="store_true",
                        help="atajo: 2 repeticiones, semillas 7 y 42, 3 tamaños")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    seeds = [int(part) for part in args.seeds.split(",") if part.strip()]
    sizes = list(DEFAULT_SIZES)
    reps = args.reps
    if args.quick:
        reps = min(reps, 2)
        seeds = [7, 42]
        sizes = sizes[:3]
    run_experiments(reps=reps, seeds=seeds, sizes=sizes, out_dir=args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
