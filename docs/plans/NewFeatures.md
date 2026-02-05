- Small Features
  - show_ticket should also take a list of tickets
  - Rename src.main to bee.main or something so that its more clear its the bees server in ps
  - Clone bees
  - Bug: MCP does not start if DB is corrupt. It should start but refuse to respond to commands with a friendly message
  - Make MCP server method names cleaner (bees-do-thing to do-thing)
  - Custom thinking verbs
  - remove owner, priority from tickets
  - make sure status is a singleton - add linter rules

- Medium Features
  - A simple tool (or MCP command) for determining the dependency order of a set of tickets

- Quality
  - git hook to run tests as CI
  - improve make-task and do-task with more instructions - check old tests for broken
  - get this working: claude mcp add bees
 
- Re-architecture
  - Is there a watcher? Remove it. Add design requirement of no daemons

- Apiary Workflow
  - YOLO mode
  - Orchestrator that builds all Epics for an Egg?
  - Use bees dependency chains to describe agent workflows (not skills)
  - Refactor skills
    - doc guidelines for maker
    - test guidelines for maker
    - reviewer for tests
    - reviewer for Epics, Tasks and Subtaskes (against egg)
    - reviewer for Eggs. Looks for under-specification in PRD and Asks User for more clarity to stop it from just inventing stuff  
    - hatch egg == docs-to-epics
    - do-epic skill: if I have suggestions make them Tasks dont just do them!
    - Summary to show status of work on an Epic, across Epics - easy to get lost
    - do-epic: SHow user acceptance criteria better (hidden behind the fold)
    - do-epic: clear guidance on how to find next epic when user does not specify
    - do-epic pause and restart (will it pickup previous work?)




  




