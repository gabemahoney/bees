**# Product Requirements Document

## Overview

epic.md is a ticket management system designed for LLMs.
Persistence is entirely in markdown files.
An MCP server is used to edit and query the md files.
A linter ensures manual edits to the md files conform to the schema.

## Features

### Schema
Three types of tickets: Epic, Task, Subtask
Epics can have Tasks, Tasks can have Subtasks.

Each ticket is its own markdown file.
Each ticket has yaml front matter for meta data that includes:
- type: epic, task or subtask
- id: a short ID for this ticket, 4 random alphanumerical characters, linter catches duplicates
- down_dependencies: a list of other ticket that it depends on
- up_dependencies: a list of other tickets that depend on it
- parent
- children
- title: short human readable title
- labels: a list of text labels

There is no status field with hard coded status enums, its all done freeform with labels

### Dependencies
Tickets of the same type can be dependant on each other.
Epic dependant on Epic. Type dependant on Type.
Tickets of different types can not be dependant on each other.

### Storage
Files are all stored in a directory of the consuming project (not this repo):
/tickets
    /epics
    /tasks
    /subtasks

But this directory structure can be assumed by this project when looking for tickets.


### MCP access
MCP access to write ensures tickets stay well formed
- Stores bidirectional dependencies in paren/child and up/down dependency fields in all tickets
- All relationship fields (parent, children, up_dependencies, down_dependencies) are stored explicitly. 
- The linter enforces bidirectional consistency across all related tickets.
MCP access to read (through disk commands) makes it easy for an LLM to run queries
- Could add an eventually consistent db with a daemon that checks for manual changes for speed
MCP access to delete tickets
- Delete based on a query result, delete all in query result
MCP access to add new named queries
- See queries below, the LLM can provide a name and the yaml to create a new MCP command it can call to execute that query
- Humans can also add new queries by manual editing - document how in the readme

#### Queries
MCP server supports named queries.
A query is a list of stages evaluated sequentially as a pipeline.

##### Structure
- A query is a list.
- Each element in the list is a stage.
- Each stage is a list of terms.
- Terms in a stage are ANDed together.
- Stages are evaluated in order.
- Results from each stage are held in memory and passed to the next stage.
- Results are deduplicated after every stage.
- If any stage produces an empty result set, the pipeline returns empty.

##### Stage types
- A stage is either a Search stage or a Graph stage.
- Mixing search and graph terms in the same stage is invalid.

##### Search terms
- type=<value>
- id=<value>
- title~<regex>
- label~<regex>
There may be multiple search terms of the same kind in a stage.

##### Graph terms
- down_dependencies: field which has short IDs of all tickets that depend on this one
- up_dependencies: field which has short IDs of all tickets that this depends on
- parent: field which contains short ID of the single parent of this ticket
- children: field which contains short IDs of the one or more children of this ticket

#####  OR semantics
- OR is expressed using regex alternation (|) inside a regex.
- There is no structural OR operator.

##### Negation
- Negation is expressed using regular expression syntax.
- There is no NOT operator.
- Negative lookahead is used for negation.

```
queries:
  open_beta_work_items:
    [
      ['type=epic', 'label~(?i)(beta|preview)'],
      ['children'],
      ['label~(?i)(open|in progress)']
    ]

  non_beta_items:
    [
      ['label~^(?!.*beta).*']
    ]

  open_non_preview_tasks:
    [
      ['type=task', 'label~^(?!.*preview).*', 'label~(?i)(open|in progress)']
    ]
```
- 
### Linter
A linter runs in case the user edits files manually
- Enforces child-parent relationship bidirectional consistency
- Enforces down and up dependency bidirectional consistency
- Enforces short ID format
- Enforces short ID uniqueness
- Marks DB as corrupt and files a report if it finds issues
- Catches cyclical dependencies which are not allowed
- MCP server will not run with DB corrupt

### Index
MCP generates a derived md index page where users can browse and click through to edit individual tickets
The index is not user-editable and can be regenerated at any time.




