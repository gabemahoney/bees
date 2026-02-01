# Problem Statement
Bees currently stores tickets in the Bees repo. Issues:
- Must support multiple client repos without ticket mingling
- Tickets should be stored locally with their source repo for git tracking

**Solution:** Hives - isolated ticket directories within client repos.

# Terminology
- **Client Repo**: Any repo using Bees
- **Hive**: Directory in client repo storing Bees tickets
- Multiple hives per repo supported (e.g., `tickets/backend/`, `bugs/reports/`)

# Config Storage

**Location:** `.bees/config.json` in client repo

**Schema:**
```json
{
  "hives": {
    "back_end": {
      "path": "tickets/backend/",
      "display_name": "Back end"
    }
  },
  "allow_cross_hive_dependencies": false,
  "schema_version": "1.0"
}
```

Created on-demand by first `colonize_hive` call.

# MCP Commands

## New Commands

### `colonize_hive(name: str, path: str)`
Create and register new hive.
- Creates `.bees/config.json` if needed
- Path must be an absolute path
  - If path does not exist, return err
  - Paths cannot be outside repo root
  - Trailing slash optional
- Validates unique hive name (see normalization below, hive names must be valid **after** normalization)
- When colonize_hive is called:                                                                                                          
  1. Takes user-provided name (e.g., "Back End")                                                                                         
  2. Normalizes it: replace spaces with underscores, convert to lowercase → "back_end"                                                   
  3. Stores in config:                                                                                                                   
     - Key: "back_end" (normalized, used internally)                                                                                     
     - Field: "display_name": "Back End" (original, for display)                                                                          
- If directory has existing tickets it runs the linter. If problems are found, it responds with an error
  - Error tells LLM to tell the user the tickets are somehow malformed
  - The user can go try to fix it and try again
  - Or the user can tell the LLM to run `sanitize_hive` which is potentially destructive
  - To deterministically identify what is a "ticket" we will a field to the ticket which describes the bees schema that was used to create it
    - bees_version: 1.1 
    - Any .md file with this field will be considered a ticket
- Tickets no longer need to be stored in /epic, /task or /subtask directories
  - Add logic to query them by scanning the yaml to determine their type
  - Tickets are all stored in the root of the dir
    - Queries and scans are only of the root of the dir, they never recurse directories
  - This means that its OK for hives paths to overlaps
    - hive `features` can be at `docs/features`
    - hive `future_features` can be at `docs/features/future/`
  - Hive display nane should be stored in a .hive folder in each hive
    - This way if a user ever moves the folder to somewhere else in the repo it can be re-located by scanning all folders in the repo
    - The source of truth is in the .bees/config.json. 
    - If a user changes a name in .hive without using the rename feature they are effectively breaking the system
      - Its just abandoned and lost
    - Any MCP code that cannot find a hive the LLM suggested should scan like this to re-find it
      - Once its refound, the config.json should be updated
      - If it can't be found, treat this as ususal for a missing Hive - error and alert the calling LLM
      - If a scan ever find a folder with a .hive subfolder on its scan and it does not recognize the name it does not try to add it back into the config
      - It can emit a warning in the logs about this and thats the extent of how it deals with this situation
  - Colonize creates two folders in a hive:
    - /eggs
      - This is used to store md files that describe features. Each feature is stored in a subfolder. Eg.
        - /eggs/feature1
      - We will not implement this functionality right now. Just implement the functionality to create the folder
    - /evicted
      - This can be used as a place to move tickets that are done if the calling workflow doesn't want to delete them
        

### `sanitize_hive(hive_name: str)`
Runs linter and fixes problems.
- Scans tickets in hive
- Detects linter problems and tries to fix them
- Returns report of changes made
- For a hive attempting to be colonized
  - If it can't fix them it tells the LLM to work with the user to try to fix them and does not establish the hive
- If its called on a hive that is already registered it does not de-register
  - It just marks the db as corrupt (using existing functionality to do so)

### `abandon_hive(hive_name: str)`
Stop tracking hive (files unchanged).
- Removes from config

### `rename_hive(old_name: str, new_name: str)`
Rename hive and update all tickets.
- Updates config
- Regenerates all ticket IDs: `old.bees-*` → `new.bees-*`
- Updates filenames and frontmatter
- Updates all references within all hives
  - Does this even if cross-hive references are disabled
  - This catches the case where a user might have made cross-hive references, then disabled the feature, then run rename_hive
- Expensive but rare operation
- Runs Linter after rename operation
  - marks db as corrupt (using existing functionality to do so) if linter fails

### `list_hives()`
Returns all tracked hives with ticket counts.

# Ticket ID Format

Need to be changed to include the `name` of the Hive as part of the id.

**Examples:**
- `backend.bees-abc1`
- `frontend.bees-def4`
- `my_api_layer.bees-xyz7`

                                                                                                                                     
**Normalization & Name Resolution:**                                                                                                   
                                                                                                                                         
When commands receive a `hive_name` parameter:                                                                                         
- LLM can provide either display name ("Back End") or normalized form ("back_end")                                                     
- System normalizes input and looks up by config key                                                                                    
- Example: `create_ticket(hive_name="Back End")` normalizes to "back_end" for lookup
- Ticket IDs always use the normalized config key:                                                                                       
  - Hive with display name "Back End" generates IDs: "back_end.bees-abc1"                                                                 
- Uniqueness validation:                                                                                                                 
  - Checked on normalized form only                                                                                                      
  - Cannot create both "Back End" and "back end" (both normalize to "back_end")                                                          
                                                                                                                                         
Normalization rules:
1. Replace spaces with underscores: `name.replace(' ', '_')`
2. Convert to lowercase: `name.lower()` 

**Benefits:**
- Self-routing: parse hive from ID
- Human readable
- Globally unique across all hives

## Updated Commands

### `create_ticket(hive_name: str, ...)`
- **New parameter:** `hive_name` (required)
- Generates ID: `{normalized_hive}.bees-{random}`
- The {random} part of the ID only needs to be valid for this hive

### `update_ticket(ticket_id: str, ...)`
- Hive inferred from ID (no hive parameter needed)

### `delete_ticket(ticket_id: str, ...)`
- Hive inferred from ID (no hive parameter needed)

### `execute_query(hive_names: list[str] = None, ...)`
- **New parameter:** `hive_names` - optional list of hive names
- Searches only specified hives
- If omitted, searches all known hives
  - If no hives exist, just return no tickets found
- If hive does not exist, returns an error

### `generate_index(hive_name: str = None, ...)`
- Optional `hive_name` parameter
- If omitted: re-generates for all hives
- Currently there is just one index.
  - Need to change it so that each Hive has its own index
  - It sits at the root of the hive

# Linter
A config option can be set so that tickets in one hive cannot depend on tickets in another hive.
- The existing linter needs to be modified to ensure that tickets in one hive do not depend on tickets in another hive
- The existing linter needs to be modified to ensure that tickets in one hive do not have children or parents that are in another hive

## Cross hive references
- Setting in client repo .bees/config.json determines whether cross hive dependencies are allowed or not
  - If not, the linter catches them and treats them like it does any other violation

# Migration

No migration path. We have no existing users so no need to migrate anything.
All existing tickets will be deleted.

# Notes
- There is no default hive. The LLM must specify hive whenever needed.
  - This prevents unintentional behaviour such as adding bugs to new feature hive
- There is no move ticket method
  - Intentional to keep things simple
