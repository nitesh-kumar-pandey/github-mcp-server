from fastmcp import FastMCP
import inspect

print("FastMCP methods:\n")

for name in dir(FastMCP):
    if not name.startswith("_"):
        print(name)

print("\nTool decorator:")
print(inspect.signature(FastMCP.tool))