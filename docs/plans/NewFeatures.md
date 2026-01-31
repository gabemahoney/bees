- Bug: MCP does not start if DB is corrupt. It should start but refuse to respond to commands with a friendly message
- Add a Feature Reviewer subagent who validates the work conforms to the docs
- Egg: An unhatched bee. .eggs/feature/PRD.md SRD.md etc
  - hatch egg == docs-to-epics
- do-epic skill: if I have suggestions make them Tasks dont just do them!
- Hives: container feature docs and all the bees to build them
  - Colonize: Establish hive
    - How does MCP server know about them? Config? .hive file in each folder?
    - Checks for docs, if docs dont exist this writes them with the user
  - Swarm: Do everything as one big workflow
    - docs-to-epics, make-epic, do-epic, show
    - But has to show more clear status
  - Hive state. Provides summary of where we are and whats done. I am getting lost
    - Hive list
    - Dont delete tickets, just archive the hive
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



- Bees all live in one hive, no need to breakdown by /epic, /task and /subtask
- Modify tickets via MCP (add labels, remove labels)
- Cli wrapper for humans?
- Todos: https://keep.google.com/u/0/#LIST/1Mjqmh-vPTueDoza_LvPuhjDUsLAD32gkLgM_-DQWxvgWYmfpT6mVbfmZFkU-R9c
- Custom verbs:
  - Yes, Claude Code supports project-level configuration. Instead of --global, you'd use:
  bashclaude config set thinkingVerbs '["Quantumizing", "Reticulating splines"]'
  This creates/updates a .claude/settings.json in your project directory.
  The hierarchy is typically:

  - Project settings (.claude/settings.json) override
  - Global settings (~/.claude/settings.json)
- remove owner, priority and status from tickets
- Add state but it can only contain on string (unlike labels)
- do-epic: SHow user acceptance criteria better (hidden behind the fold)
- Maybe do-task should be calling code-review and docs-review instead of do-epic for seperation of concerns
- do-epic: clear guidance on how to find next epic when user does not specify
- do-epic pause and restart (will it pickup previous work?)