# inspect_fastmcp_auth.py

import fastmcp
import fastmcp.utilities.authorization as auth

print("FastMCP version:", fastmcp.__version__)

print("\nAuthorization module:")
for name in dir(auth):
    if not name.startswith("_"):
        print(name)