"""Registro persistente de la partida (para evidencias y sustentación)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


class SessionLog:
    def __init__(self, seed: int, size_label: str) -> None:
        self.path: Path | None = None
        self._handle = None
        try:
            log_dir = Path(__file__).resolve().parent.parent / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            self.path = log_dir / f"partida_{stamp}_semilla{seed}.log"
            self._handle = self.path.open("w", encoding="utf-8")
            self._write(
                f"EL ESCAPE DE ÍCARO · semilla={seed} · mapa={size_label} · "
                f"inicio={datetime.now().isoformat(timespec='seconds')}"
            )
        except OSError:
            self._handle = None

    def _write(self, text: str) -> None:
        if self._handle:
            try:
                self._handle.write(text + "\n")
                self._handle.flush()
            except OSError:
                self._handle = None

    def write(self, game_time: float, speaker: str, category: str, text: str) -> None:
        self._write(f"[{game_time:7.2f}] {speaker:<9} {category:<11} {text}")

    def summary(self, lines: list[str]) -> None:
        self._write("")
        self._write("=" * 72)
        for line in lines:
            self._write(line)
        self._write("=" * 72)

    def close(self) -> None:
        if self._handle:
            try:
                self._handle.close()
            finally:
                self._handle = None
