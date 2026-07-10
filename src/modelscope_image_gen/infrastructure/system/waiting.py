import anyio


async def wait(seconds: float) -> None:
    await anyio.sleep(seconds)
