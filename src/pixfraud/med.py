"""Simulador educacional do ciclo de vida de uma transação com contestação (MED).

Simulação educacional baseada em documentação pública; sem integração com SPI/DICT e sem operação bancária
real. As **transições** abaixo são uma modelagem didática. Os **prazos** em :class:`MedConfig` são
*placeholders* ilustrativos — a confirmar na documentação oficial do Banco Central antes de qualquer uso
que dependa deles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import pandas as pd


class State(str, Enum):
    CREATED = "CREATED"
    AUTHORIZED = "AUTHORIZED"
    SETTLED = "SETTLED"
    FLAGGED = "FLAGGED"
    CAUTIONARY_BLOCK = "CAUTIONARY_BLOCK"
    MED_OPENED = "MED_OPENED"
    ANALYSIS = "ANALYSIS"
    RETURNED = "RETURNED"
    REJECTED = "REJECTED"
    CLOSED = "CLOSED"


TRANSITIONS: dict[State, frozenset[State]] = {
    State.CREATED: frozenset({State.AUTHORIZED, State.REJECTED}),
    State.AUTHORIZED: frozenset({State.SETTLED, State.REJECTED}),
    State.SETTLED: frozenset({State.FLAGGED, State.CLOSED}),
    State.FLAGGED: frozenset({State.CAUTIONARY_BLOCK, State.CLOSED}),  # CLOSED = falso positivo descartado
    State.CAUTIONARY_BLOCK: frozenset({State.MED_OPENED, State.CLOSED}),  # CLOSED = bloqueio liberado
    State.MED_OPENED: frozenset({State.ANALYSIS}),
    State.ANALYSIS: frozenset({State.RETURNED, State.REJECTED}),
    State.RETURNED: frozenset({State.CLOSED}),
    State.REJECTED: frozenset({State.CLOSED}),
    State.CLOSED: frozenset(),
}


class InvalidTransition(Exception):
    pass


@dataclass(frozen=True)
class MedConfig:
    """Prazos em horas. PLACEHOLDERS ilustrativos — a confirmar na documentação oficial do Banco Central."""

    cautionary_block_max_hours: float = 24.0
    analysis_max_hours: float = 72.0
    is_placeholder: bool = True


@dataclass
class MedCase:
    tx_id: str
    config: MedConfig = field(default_factory=MedConfig)
    history: list[tuple[State, pd.Timestamp, str, str]] = field(default_factory=list)

    def __post_init__(self):
        if not self.history:
            self.history.append((State.CREATED, pd.Timestamp("1970-01-01"), "system", "criada"))

    @property
    def state(self) -> State:
        return self.history[-1][0]

    @property
    def is_terminal(self) -> bool:
        return not TRANSITIONS[self.state]

    def start(self, ts: pd.Timestamp) -> "MedCase":
        self.history[0] = (State.CREATED, pd.Timestamp(ts), "system", "criada")
        return self

    def advance(self, to: State | str, ts: pd.Timestamp, actor: str = "system", note: str = "") -> "MedCase":
        to = State(to)
        if to not in TRANSITIONS[self.state]:
            raise InvalidTransition(f"{self.state.value} -> {to.value} não é permitida")
        ts = pd.Timestamp(ts)
        if ts < self.history[-1][1]:
            raise InvalidTransition("timestamp anterior ao último evento")
        self.history.append((to, ts, actor, note))
        return self

    def overdue(self, now: pd.Timestamp) -> bool:
        """Estado com prazo excedido segundo os *placeholders* de configuração."""
        st, since = self.history[-1][0], self.history[-1][1]
        hours = (pd.Timestamp(now) - since).total_seconds() / 3600
        if st == State.CAUTIONARY_BLOCK:
            return hours > self.config.cautionary_block_max_hours
        if st == State.ANALYSIS:
            return hours > self.config.analysis_max_hours
        return False


def lifecycle_for_decision(
    tx_id: str, decision: str, ts: pd.Timestamp, analyst_outcome: str | None = None, config: MedConfig | None = None
) -> MedCase:
    """Percorre o ciclo de uma transação conforme a decisão do motor e o resultado do analista humano.

    ``analyst_outcome``: ``CONFIRMED_FRAUD`` | ``FALSE_POSITIVE`` | ``None`` (ainda em análise).
    """
    ts = pd.Timestamp(ts)
    step = pd.Timedelta(minutes=1)
    case = MedCase(tx_id, config or MedConfig()).start(ts)
    t = ts
    if decision == "BLOCK":
        case.advance(State.REJECTED, t + step, "engine", "bloqueio pré-liquidação")
        return case.advance(State.CLOSED, t + 2 * step, "system")
    case.advance(State.AUTHORIZED, t + step, "engine")
    case.advance(State.SETTLED, t + 2 * step, "system")
    if decision == "APPROVE":
        return case.advance(State.CLOSED, t + 3 * step, "system")
    case.advance(State.FLAGGED, t + 3 * step, "engine", "REVIEW")
    if analyst_outcome is None:
        return case
    if analyst_outcome == "FALSE_POSITIVE":
        return case.advance(State.CLOSED, t + 4 * step, "analyst", "falso positivo")
    if analyst_outcome != "CONFIRMED_FRAUD":
        raise InvalidTransition(f"resultado de analista inválido: {analyst_outcome}")
    case.advance(State.CAUTIONARY_BLOCK, t + 4 * step, "analyst")
    case.advance(State.MED_OPENED, t + 5 * step, "analyst")
    case.advance(State.ANALYSIS, t + 6 * step, "system")
    case.advance(State.RETURNED, t + 7 * step, "system")
    return case.advance(State.CLOSED, t + 8 * step, "system")
