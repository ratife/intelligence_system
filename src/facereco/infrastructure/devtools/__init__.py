"""Outils dev/démo qui contournent volontairement les ports du Domain.

Voir `event_import.py` pour le rationale : en production, `events` et le
stockage objet sont alimentés par le système d'événements pré-existant
(§2.1) — ces fonctions ne sont donc jamais des use cases applicatifs.
"""
