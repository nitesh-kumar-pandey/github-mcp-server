import asyncio
from app.tools import mcp

async def main():
    tool = await mcp.get_tool("whoami")

    print("AUTH:")
    print(tool.auth)

    print("\nEXECUTION:")
    print(tool.execution)

    print("\nFN:")
    print(tool.fn)

asyncio.run(main())