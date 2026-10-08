"""
Static consistency checks between the /ci skill and the testplans hive it drives.

PURPOSE:
/ci (.claude/skills/ci/SKILL.md) reads and sets the status of the phase epics under the
testplans bee. bees rejects any status the hive does not allow, so every status the skill
uses must be listed in docker/testplans/.hive/identity.json.

SCOPE - Tests that belong here:
- statuses the /ci skill sets or reads on testplans epics are allowed by the testplans hive
- the skill's run-scope rules cover every status it sets

SCOPE - Tests that DON'T belong here:
- CI port and bees server identity check -> test_check_bees_server.py
- status_values validation inside bees -> test_set_status_values.py
"""

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CI_SKILL = REPO_ROOT / ".claude" / "skills" / "ci" / "SKILL.md"
TESTPLANS_IDENTITY = REPO_ROOT / "docker" / "testplans" / ".hive" / "identity.json"

# One or more inline-code words: "`failed`", "`failed` or `pupa`", "`finished`/`legendary`"
_CODE_WORDS = r"(`[\w-]+`(?:\s*(?:,|/|or)\s*`[\w-]+`)*)"

# "Set epic status to `failed`", "Set ALL epic statuses to `legendary`", "reset all to `pupa`", "marked `finished`"
_SETS_STATUS = re.compile(r"\b(?:(?:status(?:es)?|reset)\b[^`\n]*?\bto|marked)\s+" + _CODE_WORDS, re.IGNORECASE)
# Run-scope list: "- `failed` or `pupa` = needs to run."
_RUN_SCOPE_ITEM = re.compile(r"^\s*[-*]\s+" + _CODE_WORDS + r"\s*=", re.MULTILINE)


def _statuses(pattern, text):
    return {word for fragment in pattern.findall(text) for word in re.findall(r"`([\w-]+)`", fragment)}


def test_ci_skill_statuses_are_allowed_by_testplans_hive():
    """Regression b.9qc: /ci set failed phase epics to `failed`, which the testplans hive rejected."""
    skill = CI_SKILL.read_text()
    set_statuses = _statuses(_SETS_STATUS, skill)
    read_statuses = _statuses(_RUN_SCOPE_ITEM, skill)
    allowed = set(json.loads(TESTPLANS_IDENTITY.read_text())["status_values"])

    assert set_statuses, f"found no statuses set in {CI_SKILL.name}; update _SETS_STATUS to match the skill"
    assert read_statuses, f"found no run-scope statuses in {CI_SKILL.name}; update _RUN_SCOPE_ITEM to match the skill"
    # Run-scope rules must cover every status the skill sets, so a line either pattern misses shows up as a mismatch
    assert set_statuses == read_statuses, (
        f"statuses set and run-scope statuses in {CI_SKILL.name} differ (missing run-scope rule, or a pattern "
        f"missed a line): set only {sorted(set_statuses - read_statuses)}, "
        f"run-scope only {sorted(read_statuses - set_statuses)}"
    )
    used = set_statuses | read_statuses
    assert used <= allowed, f"/ci uses statuses the testplans hive rejects: {sorted(used - allowed)}"
