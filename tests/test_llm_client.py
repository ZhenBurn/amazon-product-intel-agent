from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Iterator

from app.config import Settings
from app.llm import OpenAIAnalysisClient
from app.models import Snapshot


def _snapshot() -> Snapshot:
    return Snapshot(
        product_id="B09C13PZX7",
        snapshot_date="2026-11-18",
        title="Test Product",
        price=100.0,
        currency="$",
        rating=4.6,
        reviews=1000,
        sales_value=1000,
        sales_text="1K+ bought in past month",
        bullets=["bullet"],
        description="description",
        main_image="https://m.media-amazon.com/images/I/x._AC_SL1500_.jpg",
        gallery_images=["https://m.media-amazon.com/images/I/y._AC_SL1500_.jpg"],
        in_stock=True,
        availability="In Stock",
        data_gaps=[],
    )


def _content(summary: str) -> str:
    return json.dumps(
        {
            "title": "测试",
            "summary": summary,
            "price_trend": "价格持平",
            "sales_trend": "销量持平",
            "key_changes": [],
            "actions": [],
            "confidence": "medium",
            "data_gaps": [],
        },
        ensure_ascii=False,
    )


class _Handler(BaseHTTPRequestHandler):
    content = _content("价格 $100.00，评价 1000")

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        body = {
            "id": "test",
            "object": "chat.completion",
            "created": 0,
            "model": "test",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": self.content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 10,
                "total_tokens": 20,
            },
        }
        payload = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        return


@contextmanager
def _server(content: str) -> Iterator[str]:
    _Handler.content = content
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _client(base_url: str) -> OpenAIAnalysisClient:
    settings = Settings(
        llm_mode="real",
        llm_base_url=base_url,
        llm_api_key="test",
        llm_model="test",
    )
    return OpenAIAnalysisClient(settings)


def test_real_client_accepts_grounded_output() -> None:
    with _server(_content("价格 $100.00，评价 1000")) as base_url:
        analysis = _client(base_url).analyze({}, _snapshot(), [_snapshot()])
    assert analysis.title == "测试"
    assert analysis.confidence == "medium"


def test_real_client_falls_back_on_unsupported_number() -> None:
    with _server(_content("价格下降了 50%")) as base_url:
        client = _client(base_url)
        analysis = client.analyze({}, _snapshot(), [_snapshot()])
        usage = client.last_usage
    assert analysis.title == "分析降级"
    assert analysis.confidence == "low"
    assert any("未溯源数字" in gap for gap in analysis.data_gaps)
    assert usage is not None and usage["total_tokens"] == 20
