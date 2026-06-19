# # # from fastmcp import FastMCP
# # # import inspect

# # # m = FastMCP("test")

# # # print("FastMCP:", type(m))
# # # print("tool signature:")
# # # print(inspect.signature(m.tool))

# # from fastmcp import FastMCP

# # m = FastMCP("test")

# # print("Has get_context:", hasattr(m, "get_context"))
# # print("Has context:", hasattr(m, "context"))

# # for attr in dir(m):
# #     if "context" in attr.lower():
# #         print(attr)

# import fastmcp
# import inspect

# print("FastMCP version:", getattr(fastmcp, "__version__", "unknown"))

# try:
#     from fastmcp.server.auth import AuthCheck
#     print("AuthCheck:", AuthCheck)
#     print("AuthCheck signature:", inspect.signature(AuthCheck))
# except Exception as e:
#     print("AuthCheck error:", e)

# try:
#     import fastmcp.server.auth as auth
#     print("\nAuth module members:")
#     for x in dir(auth):
#         if not x.startswith("_"):
#             print(x)
# except Exception as e:
#     print("Auth module error:", e)

# test_fastmcp4.py

from fastmcp.utilities.authorization import AuthContext
import inspect

print(AuthContext)

try:
    print(inspect.signature(AuthContext))
except Exception as e:
    print(e)

print("\nAttributes:")
print(dir(AuthContext))