"""
Representation boundary for Aether.

A Representation is the provider-independent result of perception.
It carries the numerical vector together with the identity of the
encoder that produced it, without imposing model-specific behavior.
"""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Representation:
    """
    Provider-independent representation produced by a perception encoder.

    Attributes:
        vector: One-dimensional float32 representation vector.
        encoder_id: Stable identifier for the encoder/model that produced it.

    The representation itself contains no inference, learning, normalization,
    or decision-making logic. It is only the boundary object between
    perception and downstream cognitive systems.
    """

    vector: np.ndarray
    encoder_id: str

    def __post_init__(self) -> None:
        vector = np.asarray(self.vector, dtype=np.float64)

        if vector.ndim != 1:
            raise ValueError("Representation vector must be 1-D")

        if not isinstance(self.encoder_id, str) or not self.encoder_id:
            raise ValueError(
                "Representation encoder_id must be a non-empty string"
            )

        object.__setattr__(self, "vector", vector)

    @property
    def dimension(self) -> int:
        """Return the dimensionality of the representation vector."""
        return int(self.vector.shape[0])

    def copy_vector(self) -> np.ndarray:
        """
        Return an independent copy of the underlying vector.

        Downstream systems should use this when they need mutable numerical
        data without mutating the Representation boundary object.
        """
        return self.vector.copy()
