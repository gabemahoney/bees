# Master Plan Deletion Plan

**Document**: `docs/plans/master_plan.md`
**Current Size**: 3,644 lines
**Target Size**: ~1,500 lines
**Estimated Reduction**: ~2,144 lines (59%)

## Execution Instructions

This plan is organized by line number in **descending order** (delete from bottom to top) to prevent line number shifts during execution. Each section lists the line ranges and what to remove.

---

## Category 1: Design Patterns and Meta Sections

**Total lines to remove: ~205**

| Line Range | Section | Description |
|------------|---------|-------------|
| 3518-3542 | Design Decisions | File System Watcher design decisions |
| 3356-3387 | Design Decisions | Named Query system design decisions |
| 3269-3289 | Design Rationale | Bidirectional validation rationale (duplicate) |
| 3247-3267 | Design Rationale | Bidirectional validation rationale |
| 3130-3162 | Design Decisions | Linter design decisions |
| 2729-2753 | Alternative Designs | Graph Executor alternatives |
| 2506-2542 | Design Decisions | Search Executor design decisions |
| 2334-2371 | Design Decisions | Query Parser design decisions with alternatives |
| 611-641 | Design Rationale | Three-tier hierarchy rationale |
| 168-201 | Design Patterns | Entire design patterns section |
| 5-9 | Documentation Philosophy | Meta-commentary section |

---

## Category 2: Design Justifications (Rationale, Alternatives, Trade-offs)

**Total lines to remove: ~320**

| Line Range | Section | Description |
|------------|---------|-------------|
| 2366-2371 | Alternatives Considered | Query Parser alternatives |
| 2021-2026 | Alternatives Considered | delete_ticket alternatives continued |
| 1958-2019 | Alternatives Considered | delete_ticket alternatives (extensive) |
| 1893-1956 | Design Decision | Orphaned subtasks decision |
| 1238-1267 | Alternatives Considered | create_ticket alternatives |
| 1097-1100 | Alternatives Considered | Tool schema alternatives |
| 1021-1024 | Alternatives Considered | Health check alternatives |
| 975-978 | Alternatives Considered | Server lifecycle alternatives |
| 944-947 | Alternatives Considered | FastMCP alternatives |
| 914-920 | Alternatives Considered | HTTP transport alternatives |
| 859-912 | Rationale | HTTP request handling rationale |
| 844-857 | Rationale | HTTP endpoint routing rationale |
| 678-690 | Design Decision | HTTP transport design decision and rationale |
| 420-423 | Design Rationale | Data models rationale |
| 360-392 | Design Rationale | Path integration rationale |
| 341-344 | Alternatives Considered | Factory functions alternatives |
| 335-344 | Design Rationale | Factory functions rationale |
| 303-306 | Alternatives Considered | File writing alternatives |
| 298-306 | Design Rationale | File writing rationale |
| 275-278 | Alternatives Considered | YAML serialization alternatives |
| 269-278 | Design Rationale | YAML serialization rationale |
| 250-253 | Alternatives Considered | ID generation alternatives |
| 244-253 | Design Rationale | ID generation rationale |
| 198-199 | Rationale | File locking rationale |
| 192-193 | Rationale | Write-ahead logging rationale |
| 186-187 | Rationale | MCP tool integration rationale |
| 180-181 | Rationale | Corruption state rationale |
| 174-175 | Rationale | Bidirectional relationship rationale |
| 162-166 | Trade-offs | Integration testing trade-offs |
| 135-144 | Design Decision | Integration testing decision and rationale |
| 101-110 | Design Decision | Host validation decision and rationale |
| 67-78 | Design Decision | Port validation decision and rationale |
| 42-62 | Design Decision | Centralized config decision, rationale, and migration |

---

## Category 3: Testing Strategy Sections

**Total lines to remove: ~280**

| Line Range | Section | Description |
|------------|---------|-------------|
| 3640-3644 | Testing | Exception handling testing |
| 3229-3231 | Testing Strategy | Bidirectional validation testing |
| 2994-3025 | Testing Strategy | Pipeline Evaluator testing strategy |
| 2717-2727 | Testing | Graph Executor testing |
| 2291-2314 | Testing Strategy | Query Parser testing strategy |
| 2028-2055 | Testing Strategy | delete_ticket testing |
| 1966-2019 | Testing Strategy | update_ticket testing (extensive) |
| 1506-1541 | Testing Coverage | Relationship sync testing coverage |
| 1471-1473 | Testing Coverage | Relationship sync testing |
| 1355-1365 | Test Infrastructure | MCP server test infrastructure |
| 1319-1365 | Testing Strategy | MCP server testing (comprehensive) |
| 1245-1267 | Testing Strategy | create_ticket testing |
| 715-728 | Testing Methodology | HTTP transport testing and results |
| 458-463 | Test Infrastructure | Reader module test infrastructure |
| 425-463 | Testing Strategy | Reader module testing (entire section) |
| 369-374 | Test Coverage | Path integration test coverage |
| 132-166 | Testing Strategy | Integration testing strategy (comprehensive) |
| 124-130 | Testing Strategy | Host validation testing |
| 90-96 | Testing Strategy | Port validation testing |

---

## Category 4: Implementation Details and Code Examples

**Total lines to remove: ~850**

| Line Range | Section | Description |
|------------|---------|-------------|
| 3589-3637 | Implementation | Exception handling architecture |
| 3546-3585 | Implementation | File watcher error handling details |
| 3500-3516 | Implementation | File watcher integration with Watchdog |
| 3481-3496 | Implementation | File watcher shutdown pattern code |
| 3451-3477 | Implementation | File watcher threading details |
| 3440-3447 | Implementation | File watcher architecture |
| 3339-3354 | Implementation | Named Query error handling |
| 3317-3335 | Implementation | Named Query integration |
| 3304-3313 | Implementation | Named Query components |
| 3211-3227 | Implementation | Bidirectional validation logic walkthrough |
| 3197-3205 | Implementation | Cyclical dependency algorithm |
| 3096-3128 | Implementation | Linter component implementation |
| 2941-2954 | Implementation | Pipeline deduplication implementation |
| 2909-2937 | Implementation | Pipeline routing logic |
| 2883-2905 | Implementation | Pipeline detection logic |
| 2843-2879 | Implementation | Pipeline stage execution flow |
| 2812-2839 | Implementation | Pipeline ticket loading walkthrough |
| 2787-2808 | Implementation | Pipeline data structure design |
| 2765-2783 | Implementation | Pipeline component architecture code |
| 2691-2711 | Implementation | Graph executor field lookup strategy |
| 2661-2687 | Implementation | Graph executor data structure design |
| 2612-2657 | Implementation | Graph executor edge case handling |
| 2554-2608 | Implementation | Graph executor relationship handling |
| 2468-2504 | Implementation | Search executor execute method walkthrough |
| 2404-2464 | Implementation | Search executor filter methods |
| 2318-2332 | Implementation | Query parser performance with code |
| 2242-2270 | Implementation | Query parser error handling examples |
| 2220-2238 | Implementation | Query parser graph term validation |
| 2176-2216 | Implementation | Query parser search term validation |
| 2145-2172 | Implementation | Query parser stage purity examples |
| 2116-2141 | Implementation | Query parser term detection logic |
| 2092-2112 | Implementation | Query parser example queries |
| 1759-1891 | Implementation | delete_ticket implementation details (~130 lines) |
| 1575-1755 | Implementation | update_ticket implementation details (~180 lines) |
| 1547-1572 | Implementation | Relationship sync future enhancements |
| 1489-1505 | Implementation | File locking implementation |
| 1104-1237 | Implementation | create_ticket implementation walkthrough |
| 1028-1095 | Implementation | Tool schema implementation walkthrough |
| 990-1020 | Implementation | Health check implementation details |
| 730-841 | Implementation | HTTP transport code walkthrough |
| 696-713 | Implementation | HTTP curl testing examples |
| 508-558 | Code Examples | YAML frontmatter examples |
| 486-500 | Code Block | Sample ticket directory layout |
| 146-161 | Implementation | Integration testing implementation |
| 112-123 | Implementation | Host validation implementation |
| 80-89 | Implementation | Port validation implementation |

---

## Category 5: Large Removable Sections

**Total lines to remove: ~359**

| Line Range | Section | Description |
|------------|---------|-------------|
| 3389-3424 | Future Enhancements | Named Query future enhancements |
| 3291-3296 | Future Considerations | General future considerations |
| 3066-3086 | Future Enhancements | Pipeline future enhancements |
| 2964-2992 | Performance | Performance and error handling |
| 2956-2962 | Optimization | Execution optimization |
| 2713-2715 | Performance | Performance and integration note |
| 2544-2546 | Performance | Performance and testing note |
| 2316-2332 | Performance | Performance considerations with benchmarks |
| 1543-1572 | Future Enhancements | Relationship sync future enhancements |
| 1402-1441 | Deployment | Deployment considerations section |
| 643-660 | Bidirectional | Bidirectional relationships subsection |
| 582-609 | Integration | Integration with reader/parser |
| 563-580 | Relationships | Relationship linking approach |
| 502-561 | YAML Format | YAML frontmatter format choices |
| 473-643 | Sample Implementation | Sample Ticket Implementation (~170 lines) |

---

## Category 6: Duplicated Content - Consolidation Required

**Total lines to remove: ~130 (after consolidation)**

### HTTP Transport (2 instances - consolidate)
- Lines 1367-1441: HTTP Configuration Architecture (duplicate)
- Lines 676-921: HTTP Transport Architecture (keep as primary)
- **Action**: Remove lines 1367-1441, retain 676-921

### Bidirectional Relationships (4+ instances - consolidate)
- Lines 172-176: Design Patterns section
- Lines 643-660: Sample Ticket Implementation
- Lines 3207-3289: Linter validation (contains 2 duplicate explanations)
- Lines 1443-1541: Relationship Synchronization Module (most comprehensive)
- **Action**: Keep 1443-1541, remove others (covered in other categories)

### Configuration Module (scattered - consolidate)
- Lines 1269-1317: Server Configuration (merge into main config discussion)
- Lines 40-66: Main configuration architecture (keep)
- **Action**: Remove 1269-1317, consolidate into 40-66

### File Locking (2 instances - consolidate)
- Lines 196-200: Design Patterns overview
- Lines 1483-1541: Detailed implementation
- **Action**: Remove 196-200 (covered in Design Patterns removal)

---

## Summary by Category

| Category | Estimated Lines | Percentage |
|----------|----------------|------------|
| Design Patterns & Meta | 205 | 10% |
| Design Justifications | 320 | 15% |
| Testing Strategies | 280 | 13% |
| Implementation Details | 850 | 40% |
| Large Removable Sections | 359 | 17% |
| Duplicated Content | 130 | 5% |
| **Total Estimated Removal** | **~2,144** | **59%** |

---

## Post-Deletion Verification Checklist

After executing deletions, verify:

1. **Line count**: Document should be ~1,500 lines (±100)
2. **Architecture intact**: All component descriptions present
3. **No broken references**: No references to removed sections
4. **Logical flow**: Document reads coherently without gaps
5. **Essential content preserved**:
   - Component list and descriptions
   - How components interact
   - Data structures and schemas
   - High-level architecture decisions (without justifications)

---

## Content to Preserve

The following sections must remain intact:

- **Architecture Overview** (lines 11-39)
- **Module Integration** (lines 202-226)
- **Component descriptions** (high-level what/how, no code)
- **Data structures and schemas**
- **Query system structure** (without implementation details)
- **MCP tool interfaces** (without implementation walkthroughs)

---

## Execution Notes

1. Work from **bottom to top** (highest line numbers first)
2. Delete entire sections, not individual lines
3. Preserve section headers for architecture components
4. Remove only content listed in this plan
5. After each major deletion, verify document structure
6. Final pass: remove orphaned section headers and fix spacing
