# inspect_fn_signature.py

import asyncio
import inspect
from app.tools import mcp

async def main():
    tool = await mcp.get_tool("whoami")

    print(inspect.signature(tool.fn))
    print()
    print(tool.fn.__annotations__)

asyncio.run(main())