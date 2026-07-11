# pyright: reportMissingImports=false
from io import BytesIO

from PIL import Image


class DummyAsyncClient:
    def __init__(self, *args, **kwargs):
        return None

    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeResponse:
    def __init__(self, *, status_code=200, headers=None, json_data=None, text="", content: bytes = b""):
        self.status_code = status_code
        self.headers = headers or {}
        self._json_data = json_data or {}
        self.text = text
        self.content = content

    def json(self):
        return self._json_data


def png_bytes_rgba() -> bytes:
    image = Image.new("RGBA", (2, 2), (255, 0, 0, 128))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
