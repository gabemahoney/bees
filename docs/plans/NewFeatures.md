- Quality
  - git hook to run tests as CI
  - improve make-task and do-task with more instructions - check old tests for broken
- Is there a watcher? Remove it. Add design requirement of no daemons
- Clone bees
- get this working: claude mcp add bees
- Cross-hive dependency setting should be per hive (stored in .hive)
- Make-task: Add detailed instructions for docs and tests
- Add agent that reviews Made Epics, Tasks and Subtasks agains the source docs
  - Looks for under-specification in PRD and Asks User for more clarity to stop it from just inventing stuff
- Bug: MCP does not start if DB is corrupt. It should start but refuse to respond to commands with a friendly message
- Add a Feature Reviewer subagent who validates the work conforms to the docs
- Use bees dependency chains to describe agent workflows (not skills)
- Optional repo param if roots is not available
- Egg: An unhatched bee. .eggs/feature/PRD.md SRD.md etc
  - hatch egg == docs-to-epics
- do-epic skill: if I have suggestions make them Tasks dont just do them!
- Hives: container feature docs and all the bees to build them
  - Colonize: Establish hive
    - How does MCP server know about them? Config? .hive file in each folder?
  - Swarm: Do everything as one big workflow
    - docs-to-epics, make-epic, do-epic, show
    - But has to show more clear status
  - Hive state. Provides summary of where we are and whats done. I am getting lost
    - Hive list
    - Dont delete tickets, just archive the hive
- A simple tool (or MCP command) for determining the dependency order of a set of tickets
- Change the bees server mounting prefix from "bees" to an empty string "" or a shorter alternative, which would transform tool names from bees__colonize_hive to just colonize_hive (or b_colonize_hive with a single-letter prefix). This is a simple one-line change in the MCP server configuration where the bees server is mounted.
- Similar to bd-prime. How to let agents know about features? Make it an MCP method 
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

                                                                                              
❯ /cost                                                                                       
  ⎿  Total cost:            $149.23                                                           
     Total duration (API):  10h 9m 2s                                                         
     Total duration (wall): 1d 4h 31m                                                         
     Total code changes:    15225 lines added, 2893 lines removed                             
     Usage by model:                                                                          
             claude-haiku:  3.2m input, 135.2k output, 2.0m cache read, 1.2m cache write      
     ($5.57)                                                                                  
            claude-sonnet:  62.6k input, 1.4m output, 259.0m cache read, 11.8m cache write    
     ($143.66)                                                                                
                 