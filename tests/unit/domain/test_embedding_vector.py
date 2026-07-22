import math

import pytest

from facereco.domain.value_objects.embedding_vector import EMBEDDING_DIMENSION, EmbeddingVector


def _unit_vector(value_index: int = 0) -> tuple[float, ...]:
    values = [0.0] * EMBEDDING_DIMENSION
    values[value_index] = 1.0
    return tuple(values)


def test_accepts_normalized_vector() -> None:
    vector = EmbeddingVector(values=_unit_vector())
    assert math.isclose(sum(v * v for v in vector.values), 1.0, abs_tol=1e-6)


def test_rejects_wrong_dimension() -> None:
    with pytest.raises(ValueError):
        EmbeddingVector(values=(1.0, 0.0))


def test_rejects_non_normalized_vector() -> None:
    values = [2.0] + [0.0] * (EMBEDDING_DIMENSION - 1)
    with pytest.raises(ValueError):
        EmbeddingVector(values=tuple(values))


def test_from_raw_normalizes() -> None:
    raw = [3.0] + [0.0] * (EMBEDDING_DIMENSION - 1)
    vector = EmbeddingVector.from_raw(raw)
    assert math.isclose(vector.values[0], 1.0, abs_tol=1e-6)


def test_cosine_similarity_of_identical_unit_vectors_is_one() -> None:
    a = EmbeddingVector(values=_unit_vector(0))
    b = EmbeddingVector(values=_unit_vector(0))
    assert math.isclose(a.cosine_similarity(b), 1.0, abs_tol=1e-9)


def test_cosine_similarity_of_orthogonal_unit_vectors_is_zero() -> None:
    a = EmbeddingVector(values=_unit_vector(0))
    b = EmbeddingVector(values=_unit_vector(1))
    assert math.isclose(a.cosine_similarity(b), 0.0, abs_tol=1e-9)
