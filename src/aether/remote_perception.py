"""
Remote perception encoder for cloud-based ML inference.

Defines a transport boundary for sending image stimuli to an external inference service
and receiving vector representations. The encoder is provider-agnostic and uses only
Python standard library networking.

Architecture:
    AetherCognitiveCore
          |
          | PerceptionEncoder (abstract)
          v
    RemotePerceptionEncoder
          |
          | HTTP POST / JSON
          v
    External inference service (Modal, Hugging Face, AWS, etc.)
"""

import base64
import json
import os
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np

from .perception import PerceptionEncoder


class RemotePerceptionError(Exception):
    """
    Raised when remote perception fails.
    
    Covers:
    - file I/O errors
    - network errors
    - HTTP errors
    - invalid responses
    - malformed JSON
    - missing or invalid embeddings
    """
    pass


class RemotePerceptionEncoder(PerceptionEncoder):
    """
    Perception encoder that sends image stimuli to a remote inference service.
    
    This encoder defines a provider-agnostic HTTP/JSON transport boundary.
    The actual model and inference logic run on the remote service.
    
    Contract:
    
    Request:
        POST {endpoint}
        Content-Type: application/json
        Authorization: Bearer <api_key> (if api_key provided)
        
        {
            "input_type": "image",
            "filename": "<original filename>",
            "data_base64": "<base64 encoded image bytes>"
        }
    
    Response:
        {
            "embedding": [0.123, 0.456, ...]
        }
    
    Usage:
        encoder = RemotePerceptionEncoder(
            endpoint="https://inference.example.com/predict",
            api_key=os.getenv("INFERENCE_API_KEY")
        )
        
        # In AetherCognitiveCore:
        core = AetherCognitiveCore(
            stimulus_source="image.png",
            perception_encoder=encoder
        )
    """

    def __init__(
        self,
        endpoint: str,
        timeout: float = 30.0,
        api_key: Optional[str] = None,
    ):
        """
        Initialize remote perception encoder.
        
        Args:
            endpoint: HTTP(S) URL of the inference service.
            timeout: Request timeout in seconds. Default: 30.
            api_key: Optional API key for authentication.
                    Will be sent as: Authorization: Bearer <api_key>
                    Never logged or included in the request body.
        """
        self.endpoint = endpoint
        self.timeout = timeout
        self.api_key = api_key

    def encode(self, source: str) -> Optional[np.ndarray]:
        """
        Send an image stimulus to the remote service and return the embedding.
        
        Args:
            source: Local file path to the image stimulus.
            
        Returns:
            numpy array (dtype float32, shape (N,)) containing the embedding,
            or None if the source is unsupported (not an image file).
            
        Raises:
            RemotePerceptionError: If the file cannot be read, the network
                                  request fails, or the response is invalid.
        """
        source_path = Path(source)

        # Check if file exists and is readable
        if not source_path.exists():
            raise RemotePerceptionError(f"Source file not found: {source}")

        if not source_path.is_file():
            raise RemotePerceptionError(f"Source is not a file: {source}")

        # Only handle image files
        image_extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'}
        if source_path.suffix.lower() not in image_extensions:
            return None

        # Read and encode the image file
        try:
            with open(source_path, 'rb') as f:
                image_bytes = f.read()
        except OSError as e:
            raise RemotePerceptionError(f"Cannot read source file: {e}") from e

        if not image_bytes:
            raise RemotePerceptionError(f"Source file is empty: {source}")

        # Encode as base64
        data_base64 = base64.b64encode(image_bytes).decode('ascii')

        # Build the request
        payload = {
            "input_type": "image",
            "filename": source_path.name,
            "data_base64": data_base64,
        }

        # Prepare HTTP request
        headers = {
            "Content-Type": "application/json",
        }

        # Add authorization if api_key is provided
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        json_data = json.dumps(payload).encode('utf-8')

        try:
            request = Request(
                self.endpoint,
                data=json_data,
                headers=headers,
                method='POST'
            )

            # Send request
            with urlopen(request, timeout=self.timeout) as response:
                response_data = response.read().decode('utf-8')

        except HTTPError as e:
            raise RemotePerceptionError(
                f"HTTP error {e.code} from {self.endpoint}"
            ) from e
        except URLError as e:
            raise RemotePerceptionError(
                f"Network error connecting to {self.endpoint}: {e.reason}"
            ) from e
        except Exception as e:
            raise RemotePerceptionError(
                f"Request failed: {e}"
            ) from e

        # Parse response JSON
        try:
            response_json = json.loads(response_data)
        except json.JSONDecodeError as e:
            raise RemotePerceptionError(
                f"Invalid JSON response from {self.endpoint}"
            ) from e

        # Extract embedding
        if "embedding" not in response_json:
            raise RemotePerceptionError(
                "Response missing 'embedding' field"
            )

        embedding = response_json["embedding"]

        # Validate embedding
        if not isinstance(embedding, (list, tuple)):
            raise RemotePerceptionError(
                f"Embedding must be a list, got {type(embedding)}"
            )

        if len(embedding) == 0:
            raise RemotePerceptionError("Embedding is empty")

        # Convert to numpy array
        try:
            embedding_array = np.array(embedding, dtype=np.float32)
        except (ValueError, TypeError) as e:
            raise RemotePerceptionError(
                f"Cannot convert embedding to float array: {e}"
            ) from e

        # Validate it's 1-D
        if embedding_array.ndim != 1:
            raise RemotePerceptionError(
                f"Embedding must be 1-D, got shape {embedding_array.shape}"
            )

        return embedding_array
