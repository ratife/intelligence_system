"""Use case du tableau de bord : restituer l'état chiffré du système.

Orchestration volontairement minimale — c'est une lecture, pas un pipeline. Elle
existe malgré tout comme use case pour que l'Interface ne dépende jamais
directement d'un adapter, et pour offrir le point d'accroche naturel des
évolutions attendues (filtrage par période, restriction par acteur).
"""

from __future__ import annotations

from facereco.domain.ports.statistics import StatisticsPort
from facereco.domain.value_objects.system_statistics import SystemStatistics


class GetSystemStatisticsUseCase:
    def __init__(self, statistics: StatisticsPort) -> None:
        self._statistics = statistics

    def execute(self) -> SystemStatistics:
        return self._statistics.collect()
