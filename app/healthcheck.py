from __future__ import annotations

import asyncio


async def check_host(host: str, mode: str, timeout_seconds: float) -> tuple[bool, str]:
    if mode == "none":
        return True, "health check disabled"

    if mode != "ping":
        return False, f"unsupported health check mode: {mode}"

    try:
        process = await asyncio.create_subprocess_exec(
            "ping",
            "-c",
            "1",
            "-W",
            str(max(1, int(timeout_seconds))),
            host,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            code = await asyncio.wait_for(process.wait(), timeout=timeout_seconds + 1)
        except TimeoutError:
            process.kill()
            await process.wait()
            return False, "ping timed out"
        return (code == 0, "ping ok" if code == 0 else "ping failed")
    except FileNotFoundError:
        return False, "ping executable is not installed"
