---
id: bugs.bees-s3d
type: subtask
title: Add parent= to SEARCH_TERMS in QueryParser
description: '**Context**: The QueryParser class in src/query_parser.py defines valid
  search terms in the SEARCH_TERMS set (line 39). Currently it only includes ''type='',
  ''id='', ''title~'', ''label~''. We need to add ''parent='' as a valid search term.


  **What to Change**:

  - In `/Users/gmahoney/projects/bees/src/query_parser.py`, line 39, add ''parent=''
  to the SEARCH_TERMS set

  - Update docstring (lines 25-29) to include parent= in the list of search terms

  - Update error message in _validate_stage method (line 141) to include parent= in
  the valid search terms list


  **Requirements**:

  - Add ''parent='' to SEARCH_TERMS set: `SEARCH_TERMS = {''type='', ''id='', ''title~'',
  ''label~'', ''parent=''}`

  - Update docstring to list parent= as a search term

  - Error messages will automatically include parent= since they reference self.SEARCH_TERMS


  **Acceptance Criteria**:

  - SEARCH_TERMS set includes ''parent=''

  - Class docstring lists parent= in search terms

  - _validate_search_term method needs to handle ''parent='' prefix (add validation
  similar to id= term)


  **Reference**: Parent Task bugs.bees-yom'
down_dependencies:
- bugs.bees-3k7
- bugs.bees-7ue
- bugs.bees-fmj
- bugs.bees-sil
parent: bugs.bees-yom
created_at: '2026-02-03T07:18:19.439320'
updated_at: '2026-02-03T07:21:34.288086'
status: completed
bees_version: '1.1'
---

**Context**: The QueryParser class in src/query_parser.py defines valid search terms in the SEARCH_TERMS set (line 39). Currently it only includes 'type=', 'id=', 'title~', 'label~'. We need to add 'parent=' as a valid search term.

**What to Change**:
- In `/Users/gmahoney/projects/bees/src/query_parser.py`, line 39, add 'parent=' to the SEARCH_TERMS set
- Update docstring (lines 25-29) to include parent= in the list of search terms
- Update error message in _validate_stage method (line 141) to include parent= in the valid search terms list

**Requirements**:
- Add 'parent=' to SEARCH_TERMS set: `SEARCH_TERMS = {'type=', 'id=', 'title~', 'label~', 'parent='}`
- Update docstring to list parent= as a search term
- Error messages will automatically include parent= since they reference self.SEARCH_TERMS

**Acceptance Criteria**:
- SEARCH_TERMS set includes 'parent='
- Class docstring lists parent= in search terms
- _validate_search_term method needs to handle 'parent=' prefix (add validation similar to id= term)

**Reference**: Parent Task bugs.bees-yom
