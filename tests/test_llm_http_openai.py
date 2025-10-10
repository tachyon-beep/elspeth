import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from elspeth.plugins.llms.openai_http import HttpOpenAIClient


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("content-length", "0"))
        body = self.rfile.read(length)
        payload = json.loads(body)
        assert payload["messages"][0]["role"] == "system"
        assert payload["messages"][1]["role"] == "user"
        response = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "mocked response",
                    }
                }
            ]
        }
        blob = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)

    def log_message(self, *args, **kwargs):  # noqa: ARG002
        return


@pytest.fixture()
def http_server():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join()


def test_http_openai_client_roundtrip(http_server):
    host, port = http_server.server_address
    client = HttpOpenAIClient(api_base=f"http://{host}:{port}", model="test-model")
    result = client.generate(system_prompt="sys", user_prompt="hello", metadata={"k": "v"})
    assert result["content"] == "mocked response"
    assert result["metadata"] == {"k": "v"}
    assert "choices" in result["raw"]


def test_http_openai_client_env_key(monkeypatch, http_server):
    host, port = http_server.server_address
    monkeypatch.setenv("HTTP_OPENAI_KEY", "secret")
    client = HttpOpenAIClient(
        api_base=f"http://{host}:{port}",
        api_key_env="HTTP_OPENAI_KEY",
        temperature=0.1,
        max_tokens=50,
    )
    result = client.generate(system_prompt="assistant", user_prompt="hi")
    assert result["content"] == "mocked response"
