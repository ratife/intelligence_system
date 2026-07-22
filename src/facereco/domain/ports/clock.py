"""Port d'horloge — permet de tester le domaine/application sans dépendre de l'heure système."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime


class ClockPort(ABC):
    @abstractmethod
    def now(self) -> datetime:
        raise NotImplementedError
