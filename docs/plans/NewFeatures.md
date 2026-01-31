- A simple tool (or MCP command) for determining the dependency order of a set of tickets
- Similar to bd-prime. How to let agents know about features?
  1. Hook Configuration (~/.claude/settings.json):                                                                                       
  {                                                                                                                                      
    "hooks": {                                                                                                                           
      "SessionStart": [{                                                                                                                 
        "matcher": "",                                                                                                                   
        "hooks": [{"type": "command", "command": "bd prime"}]                                                                            
      }],                                                                                                                                
      "PreCompact": [{                                                                                                                   
        "matcher": "",                                                                                                                   
        "hooks": [{"type": "command", "command": "bd prime"}]                                                                            
      }]                                                                                                                                 
    }                                                                                                                                    
  }                                                                                                                                      
                                                                                                                                         
  2. When Hooks Fire:                                                                                                                    
  - SessionStart - Every time you start Claude Code                                                                                      
  - PreCompact - Before context gets compressed  


- Hives: container feature docs and all the bees to build them
- Bees all live in one hive, no need to breakdown by /epic, /task and /subtask
- Modify tickets via MCP (add labels, remove labels)
- Cli wrapper for humans?
- Hive list
- Todos: https://keep.google.com/u/0/#LIST/1Mjqmh-vPTueDoza_LvPuhjDUsLAD32gkLgM_-DQWxvgWYmfpT6mVbfmZFkU-R9c
- Custom verbs:
  - Yes, Claude Code supports project-level configuration. Instead of --global, you'd use:
  bashclaude config set thinkingVerbs '["Quantumizing", "Reticulating splines"]'
  This creates/updates a .claude/settings.json in your project directory.
  The hierarchy is typically:

  - Project settings (.claude/settings.json) override
  - Global settings (~/.claude/settings.json)