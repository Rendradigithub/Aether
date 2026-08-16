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
except ImportError:
    from radial import RadialSignature, PIL_AVAILABLE


class PerceptionEncoder:
    """
    Minimal contract for stimulus encoding.
    
    A perception encoder converts an observation source into a numpy array representation.
    """

    def encode(self, source: str) -> Optional[np.ndarray]:
        """
        Encode a stimulus source into a representation.
        
        Args:
            source: File path or observation identifier
            
        Returns:
            numpy array representation, or None if unsupported/failed
        """
        raise NotImplementedError


class RadialEncoder(PerceptionEncoder):
    """
    Radial contour-based perception encoder.
    
    Encodes image and text stimuli into 36-dimensional radial signatures.
    Preserves the exact behavior of AetherCognitiveCore._load_stimulus().
    
    Stateless: encode() has no side effects.
    """

    def encode(self, source: str) -> Optional[np.ndarray]:
        """
        Encode stimulus into 36-D radial signature.
        
        Preserves exact behavior of the historical _load_stimulus() method:
        - Image files (.png, .jpg, .jpeg, .bmp) loaded via RadialSignature.from_image()
        - Text files parsed as 36 floats and normalized
        - Unsupported inputs return None
        - Print messages and exception handling match original behavior
        
        Args:
            source: File path (image or text vector)
            
        Returns:
            36-D numpy array, or None if unsupported/failed
        """
        if source.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp')):
            if not PIL_AVAILABLE:
                print("[Error] Pillow needed")
                return None
            try:
                sig = RadialSignature.from_image(source, size=64, num_rays=36)
                print("[Stimulus] Loaded radial signature (36 rays)")
                return sig
            except Exception:
                print("[Error] Unsupported stimulus")
                return None
        else:
            try:
                with open(source) as f:
                    vec = np.array([float(x) for x in f.read().split()])
                if len(vec) == 36:
                    normalized = vec / (np.linalg.norm(vec) + 1e-8)
                    print("[Stimulus] Loaded radial signature from file")
                    return normalized
                else:
                    raise ValueError
            except:
                print("[Error] Unsupported stimulus")
                return None
