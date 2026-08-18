"""
Minimal perception encoder abstraction.

Defines a clean boundary between stimulus observation and representation encoding.
Enables swapping the current radial implementation for alternative encoders
without coupling the cognitive loop to any specific perception mechanism.
"""

from typing import Optional

import numpy as np

try:
    from .radial import RadialSignature, PIL_AVAILABLE
    from .representation import Representation
except ImportError:
    from radial import RadialSignature, PIL_AVAILABLE
    from representation import Representation


class PerceptionEncoder:
    """
    Minimal contract for stimulus encoding.

    A perception encoder converts an observation source into a
    provider-independent Representation.
    """

    def encode(self, source: str) -> Optional[Representation]:
        """
        Encode a stimulus source into a representation.

        Args:
            source: File path or observation identifier

        Returns:
            Representation, or None if unsupported/failed.
        """
        raise NotImplementedError


class RadialEncoder(PerceptionEncoder):
    """
    Radial contour-based perception encoder.

    Encodes image and text stimuli into 36-dimensional radial signatures.
    Preserves the exact behavior of AetherCognitiveCore._load_stimulus()
    while exposing the result through the Representation boundary.

    Stateless: encode() has no side effects.
    """

    def encode(self, source: str) -> Optional[Representation]:
        """
        Encode stimulus into a 36-D radial representation.

        Preserves the existing behavior:
        - Image files (.png, .jpg, .jpeg, .bmp) are loaded via
          RadialSignature.from_image()
        - Text files are parsed as 36 floats and normalized
        - Unsupported inputs return None
        - Existing print messages and exception handling are preserved

        Args:
            source: File path (image or text vector)

        Returns:
            Representation containing the radial vector, or None if
            unsupported/failed.
        """
        if source.lower().endswith((".png", ".jpg", ".jpeg", ".bmp")):
            if not PIL_AVAILABLE:
                print("[Error] Pillow needed")
                return None
            try:
                sig = RadialSignature.from_image(
                    source,
                    size=64,
                    num_rays=36,
                )
                print("[Stimulus] Loaded radial signature (36 rays)")
                return Representation(
                    vector=np.asarray(sig, dtype=np.float32),
                    encoder_id="radial",
                )
            except (FileNotFoundError, ValueError) as e:
                print(f"[Error] Failed to load image stimulus {source}: {e}")
                return None
            except Exception as e:
                if type(e).__name__ == "UnidentifiedImageError":
                    print(f"[Error] Unidentified image format for {source}: {e}")
                    return None
                print(f"[Error] Unexpected error loading image stimulus {source}: {e}")
                return None
        else:
            try:
                with open(source) as f:
                    vec = np.array([float(x) for x in f.read().split()])
                if len(vec) == 36:
                    normalized = vec / (np.linalg.norm(vec) + 1e-8)
                    print("[Stimulus] Loaded radial signature from file")
                    return Representation(
                        vector=normalized,
                        encoder_id="radial",
                    )
                else:
                    raise ValueError
            except Exception:
                print("[Error] Unsupported stimulus")
                return None
