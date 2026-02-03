#!/usr/bin/env python3
"""Test script to check which tools are registered with FastMCP."""

from src.mcp_server import mcp

# Try to access the tools registry
print("Checking registered tools...")

# FastMCP stores tools differently - let's try to inspect the server
if hasattr(mcp, '_mcp_server'):
    server = mcp._mcp_server
    print(f"Server type: {type(server)}")
    print(f"Server attributes: {dir(server)}")
    
# Check the tool cache
if hasattr(server, '_tool_cache'):
    tool_cache = server._tool_cache
    print(f"\nTool cache type: {type(tool_cache)}")
    print(f"Tool cache: {tool_cache}")
    
# Try to access fastmcp reference
if hasattr(server, '_fastmcp_ref'):
    fastmcp_ref = server._fastmcp_ref
    print(f"\nFastMCP ref: {fastmcp_ref}")
    if hasattr(fastmcp_ref, '_tools'):
        print(f"FastMCP tools: {fastmcp_ref._tools}")
        
# Try accessing the mcp object's internals
print(f"\nmcp object type: {type(mcp)}")

# Try get_tools()
if hasattr(mcp, 'get_tools'):
    import asyncio
    
    async def get_tools():
        return await mcp.get_tools()
    
    tools_dict = asyncio.run(get_tools())
    print(f"\nFound {len(tools_dict)} tools via get_tools():")
    for tool_name, tool in tools_dict.items():
        print(f"  - {tool_name}: {tool.name}")
        
# Check __all__ if it exists
if hasattr(mcp, '__all__'):
    print(f"\n__all__ contains: {mcp.__all__}")

print("\nDone!")
