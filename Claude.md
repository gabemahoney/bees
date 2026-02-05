# Purpose of this repo

You are building the bees ticket management system but also using the bees ticket system.
Bear this in mind when talking with the user. Sometimes they will be asking you to just use bees.
Other times they will be asking you to build or debug bees.

## Bees MCP Server Management (for dev and debugging)

**Start server:**
```bash
poetry run python -m src.main > /tmp/bees_server.log 2>&1 &
```

**Stop server:**
```bash
pkill -9 -f "python -m src.main"
```

**Restart server:**
```bash
pkill -9 -f "python -m src.main" && sleep 2 && poetry run python -m src.main > /tmp/bees_server.log 2>&1 &
```

**Check for duplicate servers:**
```bash
ps aux | grep "python.*src.main" | grep -v grep
```
Shows PID and start time. If multiple processes exist, kill old ones before restarting.

**Check server health:**
```bash
curl http://127.0.0.1:8000/health
```

**View logs:**
```bash
tail -f ~/.bees/mcp.log
```


MCP Roots Protocol and repo_root                                                           
                                                                                             
  Location: src/mcp_repo_utils.py                                                            
                                                                                             
  How it works:                                                                              
                                                                                             
  1. Entry point: Every MCP tool function (e.g., _create_ticket in mcp_ticket_ops.py)        
  receives ctx: Context from FastMCP                                                         
    - Line 63: ctx: Context | None = None                                                    
  2. Get repo_root: Calls get_repo_root(ctx) - mcp_repo_utils.py:104-146                     
  async def get_repo_root(ctx: Context | None) -> Path | None:                               
      if ctx:                                                                                
          client_root = await get_client_repo_root(ctx)  # Try to get from client            
          if client_root:                                                                    
              return get_repo_root_from_path(client_root)  # Verify it's a git repo          
          else:                                                                              
              return None  # Client doesn't support roots                                    
  3. Roots protocol call: get_client_repo_root(ctx) - mcp_repo_utils.py:54-102               
  async def get_client_repo_root(ctx: Context) -> Path | None:                               
      try:                                                                                   
          roots = await ctx.list_roots()  # Ask client for roots                             
          # ... extract first root and return as Path                                        
      except NotFoundError:  # Client doesn't support roots protocol                         
          return None                                                                        
                                                                                             
  No fallback:                                                                               
  - If get_repo_root() returns None, MCP tools raise error: "Your MCP client does not support
   the roots protocol"
  - It is also supposed to tell the client to provide an optional "repo_root" parameter to use with the call, so that the calling LLM can provide it explicitly if its not provided automatically by roots
  - For some reason, the Sonnet LLM was unable to make this happen. I dont think it implemented the optional param that lets a client provide the repo.
  - The error message was also supposed to tell the Client to use the optional repo_root paramater either
  - Server can't use Path.cwd() because server runs in different directory than client       
                                                                                             
  The threading problem:                                                                     
  - repo_root must be passed to ~30+ functions across 6 files:                               
    - config.py: load_bees_config(repo_root), get_config_path(repo_root)                     
    - paths.py: get_ticket_path(ticket_id, type, repo_root), infer_ticket_type_from_id(id,   
  repo_root)                                                                                 
    - writer.py: write_ticket_file(..., repo_root)                                           
    - id_utils.py: extract_existing_ids_from_all_hives(repo_root)                            
    - ticket_factory.py: create_epic(..., repo_root), create_task(..., repo_root), etc.      
  - All have signature: repo_root: Path | None = None                                        
  - Forgetting to pass it → propagates as None → eventually hits get_config_path(None) →     
  raises misleading error  

Task: My intuition is that this code could be simplified. The function call stack seems to deep
and it seems like an anti-pattern to pass a param like this. Also, can't all of these functions
use some shared code to get the repo root from Roots? I can understand if they cant use shared code to
expose the optional param and ask calling Clients to use it...