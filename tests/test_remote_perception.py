"""
Unit tests for RemotePerceptionEncoder.

Tests the HTTP/JSON transport boundary without external dependencies.
Uses a local mock HTTP server to simulate the inference service.
"""

import base64
import json
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

import numpy as np

from src.aether.remote_perception import (
    RemotePerceptionEncoder,
    RemotePerceptionError,
)


def make_handler(status_code=200, response_body='{"embedding": [0.1, 0.2, 0.3, 0.4, 0.5]}', delay=0.0):
    """
    Factory for HTTP request handler classes with configurable responses.

    The handler captures the request and stores it in class attributes
    for later inspection. It supports a delay before sending the response.
    """

    if isinstance(response_body, str):
        response_body_bytes = response_body.encode("utf-8")
    else:
        response_body_bytes = response_body

    class Handler(BaseHTTPRequestHandler):
        # Class variables for capturing request data
        request_method = None
        request_path = None
        request_headers = {}
        request_data = None

        def do_POST(self):
            # Store request info
            Handler.request_method = self.command
            Handler.request_path = self.path
            Handler.request_headers = dict(self.headers)

            content_length = int(self.headers.get("Content-Length", 0))
            Handler.request_data = self.rfile.read(content_length)

            # Optional delay before responding
            if delay > 0:
                time.sleep(delay)

            # Attempt to send the response; if the client has already closed
            # the connection (e.g., due to a timeout), just swallow the
            # expected Windows/Linux disconnect exceptions.
            try:
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(response_body_bytes)
            except (ConnectionAbortedError, BrokenPipeError):
                # Client disconnected before we could write the response.
                # This is expected in timeout tests; no need to log.
                pass

        def log_message(self, format, *args):
            # Suppress noisy server logs
            pass

    # Set attributes to avoid any closure scoping issues
    Handler.status_code = status_code
    Handler.response_body_bytes = response_body_bytes
    Handler.delay = delay

    return Handler


class TestRemotePerceptionEncoder(unittest.TestCase):
    """Test suite for RemotePerceptionEncoder."""

    def setUp(self):
        self.server = None
        self.server_thread = None
        self.url = None

    def tearDown(self):
        if self.server:
            self.server.shutdown()
            if self.server_thread and self.server_thread.is_alive():
                self.server_thread.join(timeout=1.0)
            self.server.server_close()
            self.server = None
            self.server_thread = None

    def _start_server(self, handler_class):
        """Start a local HTTP server on an ephemeral loopback port."""
        self.server = HTTPServer(("127.0.0.1", 0), handler_class)
        port = self.server.server_address[1]
        self.url = f"http://127.0.0.1:{port}"

        self.server_thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.server_thread.start()

        return self.url

    def _create_image_file(self, ext=".png", content=b"dummy image data"):
        """Create a temporary file with the given extension and content."""
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
            f.write(content)
            path = Path(f.name)
        return path

    def _assert_embedding_ok(self, embedding, expected_values=None):
        """Assert embedding is a float32 1‑D array with expected values."""
        self.assertIsInstance(embedding, np.ndarray)
        self.assertEqual(embedding.dtype, np.float32)
        self.assertEqual(embedding.ndim, 1)
        if expected_values is not None:
            np.testing.assert_array_almost_equal(
                embedding, np.array(expected_values, dtype=np.float32)
            )

    def test_successful_encoding(self):
        """Test a successful round‑trip: request contract and embedding."""
        expected_embedding = [0.1, 0.2, 0.3, 0.4, 0.5]
        handler_cls = make_handler(
            response_body=json.dumps({"embedding": expected_embedding})
        )
        self._start_server(handler_cls)

        test_file = self._create_image_file(ext=".png", content=b"test image")
        try:
            encoder = RemotePerceptionEncoder(endpoint=self.url, timeout=5.0)
            result = encoder.encode(str(test_file))
            self._assert_embedding_ok(result, expected_embedding)

            self.assertEqual(handler_cls.request_method, "POST")
            self.assertEqual(handler_cls.request_path, "/")
            self.assertEqual(
                handler_cls.request_headers.get("Content-Type"),
                "application/json",
            )
            self.assertNotIn("Authorization", handler_cls.request_headers)

            request_body = json.loads(
                handler_cls.request_data.decode("utf-8")
            )
            self.assertEqual(request_body["input_type"], "image")
            self.assertEqual(request_body["filename"], test_file.name)
            expected_b64 = base64.b64encode(b"test image").decode("ascii")
            self.assertEqual(request_body["data_base64"], expected_b64)
        finally:
            test_file.unlink()

    def test_authorization_header(self):
        """When api_key is supplied, Authorization header must be set."""
        handler_cls = make_handler()
        self._start_server(handler_cls)

        test_file = self._create_image_file(ext=".png")
        try:
            api_key = "test-api-key-123"
            encoder = RemotePerceptionEncoder(
                endpoint=self.url, api_key=api_key, timeout=5.0
            )
            _ = encoder.encode(str(test_file))

            auth_header = handler_cls.request_headers.get("Authorization")
            self.assertEqual(auth_header, f"Bearer {api_key}")

            request_body = json.loads(
                handler_cls.request_data.decode("utf-8")
            )
            self.assertNotIn("api_key", request_body)
            self.assertNotIn("Authorization", request_body)
        finally:
            test_file.unlink()

    def test_http_500_error(self):
        """HTTP 500 response must raise RemotePerceptionError."""
        handler_cls = make_handler(status_code=500)
        self._start_server(handler_cls)

        test_file = self._create_image_file()
        try:
            encoder = RemotePerceptionEncoder(endpoint=self.url)
            with self.assertRaises(RemotePerceptionError) as ctx:
                encoder.encode(str(test_file))
            self.assertIn("HTTP error 500", str(ctx.exception))
        finally:
            test_file.unlink()

    def test_invalid_json_response(self):
        """Malformed JSON response must raise RemotePerceptionError."""
        handler_cls = make_handler(response_body="not valid json {{{")
        self._start_server(handler_cls)

        test_file = self._create_image_file()
        try:
            encoder = RemotePerceptionEncoder(endpoint=self.url)
            with self.assertRaises(RemotePerceptionError) as ctx:
                encoder.encode(str(test_file))
            self.assertIn("Invalid JSON response", str(ctx.exception))
        finally:
            test_file.unlink()

    def test_missing_embedding_field(self):
        """Response without 'embedding' field must raise."""
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self):
                return json.dumps({"not_embedding": []}).encode("utf-8")

        with patch(
            "src.aether.remote_perception.urlopen",
            return_value=FakeResponse(),
        ) as mock_urlopen:
            test_file = self._create_image_file()
            try:
                encoder = RemotePerceptionEncoder(
                    endpoint="http://mock-inference"
                )

                with self.assertRaises(RemotePerceptionError) as ctx:
                    encoder.encode(str(test_file))

                self.assertIn("missing 'embedding'", str(ctx.exception))
                mock_urlopen.assert_called_once()
            finally:
                test_file.unlink()

    def test_empty_embedding(self):
        """Embedding list empty must raise."""
        handler_cls = make_handler(response_body=json.dumps({"embedding": []}))
        self._start_server(handler_cls)

        test_file = self._create_image_file()
        try:
            encoder = RemotePerceptionEncoder(endpoint=self.url)
            with self.assertRaises(RemotePerceptionError) as ctx:
                encoder.encode(str(test_file))
            self.assertIn("Embedding is empty", str(ctx.exception))
        finally:
            test_file.unlink()

    def test_embedding_not_list(self):
        """Embedding is not a list/tuple must raise."""
        handler_cls = make_handler(
            response_body=json.dumps({"embedding": "not-a-list"})
        )
        self._start_server(handler_cls)

        test_file = self._create_image_file()
        try:
            encoder = RemotePerceptionEncoder(endpoint=self.url)
            with self.assertRaises(RemotePerceptionError) as ctx:
                encoder.encode(str(test_file))
            self.assertIn("Embedding must be a list", str(ctx.exception))
        finally:
            test_file.unlink()

    def test_embedding_non_numeric(self):
        """Embedding containing non‑numeric values must raise."""
        handler_cls = make_handler(
            response_body=json.dumps({"embedding": ["not", "numbers"]})
        )
        self._start_server(handler_cls)

        test_file = self._create_image_file()
        try:
            encoder = RemotePerceptionEncoder(endpoint=self.url)
            with self.assertRaises(RemotePerceptionError) as ctx:
                encoder.encode(str(test_file))
            self.assertIn(
                "Cannot convert embedding to float array", str(ctx.exception)
            )
        finally:
            test_file.unlink()

    def test_embedding_multi_dimensional(self):
        """Embedding that results in a multi‑dimensional array must raise."""
        handler_cls = make_handler(
            response_body=json.dumps(
                {"embedding": [[0.1, 0.2], [0.3, 0.4]]}
            )
        )
        self._start_server(handler_cls)

        test_file = self._create_image_file()
        try:
            encoder = RemotePerceptionEncoder(endpoint=self.url)
            with self.assertRaises(RemotePerceptionError) as ctx:
                encoder.encode(str(test_file))
            self.assertIn("Embedding must be 1-D", str(ctx.exception))
        finally:
            test_file.unlink()

    def test_missing_source_file(self):
        """Nonexistent file must raise RemotePerceptionError."""
        encoder = RemotePerceptionEncoder(endpoint="http://localhost")
        with self.assertRaises(RemotePerceptionError) as ctx:
            encoder.encode("/nonexistent/file.png")
        self.assertIn("not found", str(ctx.exception))

    def test_unsupported_source_type(self):
        """Non‑image file should return None (not raise)."""
        encoder = RemotePerceptionEncoder(endpoint="http://localhost")
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"not an image")
            path = Path(f.name)
        try:
            result = encoder.encode(str(path))
            self.assertIsNone(result)
        finally:
            path.unlink()

    def test_empty_image_file(self):
        """Zero‑byte image file must raise RemotePerceptionError."""
        handler_cls = make_handler()
        self._start_server(handler_cls)

        empty_file = self._create_image_file(ext=".png", content=b"")
        try:
            encoder = RemotePerceptionEncoder(endpoint=self.url)
            with self.assertRaises(RemotePerceptionError) as ctx:
                encoder.encode(str(empty_file))
            self.assertIn("Source file is empty", str(ctx.exception))
        finally:
            empty_file.unlink()

    def test_timeout(self):
        """Configured timeout must be respected (timeout raises RemotePerceptionError)."""
        # Server delays longer than the encoder timeout
        handler_cls = make_handler(delay=0.5)
        self._start_server(handler_cls)

        test_file = self._create_image_file()
        try:
            encoder = RemotePerceptionEncoder(
                endpoint=self.url, timeout=0.1
            )
            with self.assertRaises(RemotePerceptionError):
                encoder.encode(str(test_file))
        finally:
            test_file.unlink()

    def test_multiple_image_extensions(self):
        """All supported image extensions should be accepted."""
        supported_extensions = (
            ".png",
            ".jpg",
            ".jpeg",
            ".bmp",
            ".gif",
            ".webp",
        )

        expected_embedding = [0.1, 0.2, 0.3]

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self):
                return json.dumps(
                    {"embedding": expected_embedding}
                ).encode("utf-8")

        with patch(
            "src.aether.remote_perception.urlopen",
            return_value=FakeResponse(),
        ) as mock_urlopen:
            for ext in supported_extensions:
                with self.subTest(ext=ext):
                    test_file = self._create_image_file(
                        ext=ext, content=b"some image"
                    )
                    try:
                        encoder = RemotePerceptionEncoder(
                            endpoint="http://mock-inference"
                        )
                        result = encoder.encode(str(test_file))

                        self._assert_embedding_ok(
                            result, expected_embedding
                        )
                    finally:
                        test_file.unlink()

            self.assertEqual(
                mock_urlopen.call_count,
                len(supported_extensions),
            )


if __name__ == "__main__":
    unittest.main()