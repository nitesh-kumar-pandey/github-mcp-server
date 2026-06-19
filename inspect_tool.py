# inspect_tool.py

import asyncio
from app.tools import mcp

async def main():
    tool = await mcp.get_tool("whoami")

    print(type(tool))

    for attr in dir(tool):
        if not attr.startswith("_"):
            print(attr)

asyncio.run(main())