"""rc_progress.py — reading RealityScan's progress file into one overall bar.

Pure module: no FastAPI import, so it stays callable from a test on a temp
directory (CLAUDE.md §2.4).

RealityScan.exe is a GUI-subsystem binary with no console of its own, so the
stdout loop in `run_rc` has never seen anything but EOF (CLAUDE.md §15.3). The
channel that does work is `-writeProgress "<file>" 1`, which writes

    <task id> <fraction> <elapsed s> <estimated remaining s> #<state>

live, a few lines a second, with `#started` / `#progress` / `#completed` and a
`#timeout` heartbeat repeating the last value when nothing has changed.

Two things had to be measured before that file could become a bar, because RS
reports **per task** and never says how many tasks there will be.

**Which verbs emit a task.** Measured on fauteuil3d_test with three throwaway
runs (`-quit` alone, `-addFolder` alone, `-set`×4 + `-addFolder`):

    41061, 41063, 41064   RS startup — present even when `-quit` is the only
                          verb in the script. Never a phase of the alignment.
    -set                  emits no task at all
    65536  (0x10000)      -addFolder                  0.19 s / 251 frames
    65537  (0x10001)      -align                     89.95 s
    20533, 20534          -selectMaximalComponent, -save   0.10 / 0.59 s
    20576  (0x5060)       -exportRegistration         9.79 s (it undistorts
                                                      and writes every image)
    20585  (0x5069)       -exportSparsePointCloud     0.37 s

**Which of the id and the ordinal is stable.** CLAUDE.md §15.3 recorded the
opposite of what a second measurement shows: the ids repeated byte for byte
across four separate processes, while the ordinals moved — `-align` was task 2
of 3 in the run that produced that note and task 5 of 9 here, because the `-set`
block and the `-save` were added in between (and because three startup tasks
were being counted as verbs). So the id is the key, and the ordinal is only the
tie-breaker for the verbs whose ids are ambiguous.

Hence the two-level match in `RCProgressTracker`: the plan comes from the
`.rscmd` this run generated, and each new task id claims the next plan entry of
its own kind when its kind is known. That resync is not theoretical — a
`-exportRegistration` RS refuses (the `err:5617` of CLAUDE.md §12, 2026-08-23)
is skipped *without failing the script*, and a bar keyed on the ordinal alone
would credit the alignment's remaining weight to the wrong phase for the rest of
the run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# `<id> <fraction> <elapsed> <remaining> #<state>`. The two clocks are doubles
# in RS's own format string and are read as floats; `#completed` lines carry
# nonsense in them (the elapsed resets to ~0 and the estimate jumps past the
# whole run), so only the fraction is trusted there.
_LINE = re.compile(
    r"^(\d+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+#(\w+)\s*$"
)

# Emitted while RS boots, before it reads the script. Three of them, all
# instantaneous, all present in a run whose entire script is `-quit`.
STARTUP_TASK_IDS = frozenset({41061, 41063, 41064})

# The verbs whose task id was pinned by measurement. Used to resync the plan
# when a verb turns out to emit no task; the ones left out (`-save` and
# `-selectMaximalComponent`, which produce 20533/20534 in an order that was not
# separable) fall through to the ordinal, and are sub-second either way.
KIND_BY_TASK_ID: dict[int, str] = {
    65536: "addFolder",
    65537: "align",
    20576: "exportRegistration",
    20585: "exportSparsePointCloud",
}

# Verbs that never produce a task, so they must not consume a plan slot.
_SILENT_VERBS = frozenset({"set", "quit"})

# Relative shares of one run. Measured end to end on fauteuil3d_test (251
# frames, 106 s): the alignment is 85 % of a script without the COLMAP export,
# and the registration export — which undistorts and rewrites every image — is
# essentially all of the rest. The numbers are relative and renormalised over
# whatever the script actually contains, so a run with two registration exports
# is weighted correctly without a second table.
#
# They live here rather than in defaults.json: they are a measurement of this
# tool, like the 5–95 % mapping of the LichtFeld bar, not a preference anyone
# would want a slider for.
WEIGHTS: dict[str, float] = {
    # Whether it emits a task at all is not measured; it is given a share
    # rather than declared silent, because a verb wrongly listed as silent
    # would shift every later phase, while a verb wrongly given a share costs
    # one percent and is corrected by the id resync at `-addFolder`.
    "clearCache": 1.0,
    "addFolder": 2.0,
    "align": 70.0,
    "mergeComponents": 1.0,
    "selectMaximalComponent": 1.0,
    "save": 2.0,
    "exportRegistration": 12.0,
    "exportSparsePointCloud": 2.0,
}
_DEFAULT_WEIGHT = 2.0

LABELS: dict[str, str] = {
    "clearCache": "Clearing the cache",
    "addFolder": "Loading the frames",
    "align": "Aligning",
    "mergeComponents": "Merging components",
    "selectMaximalComponent": "Selecting the largest component",
    "save": "Saving the project",
    "exportRegistration": "Exporting the registration",
    "exportSparsePointCloud": "Exporting the sparse cloud",
}


@dataclass(frozen=True)
class Task:
    """One expected phase of the run: a verb of the .rscmd and its share."""

    verb: str
    weight: float

    @property
    def label(self) -> str:
        return LABELS.get(self.verb, self.verb)


@dataclass(frozen=True)
class Sample:
    """What one progress line means for the step as a whole."""

    overall: float          # 0 .. 0.99 — the step is not done until run_rc says so
    task: Task
    task_fraction: float
    remaining_s: Optional[float]   # RS's own estimate for the current task
    state: str                     # started | progress | completed | timeout
    new_task: bool


def plan_from_script(script_text: str) -> list[Task]:
    """The tasks the .rscmd we just wrote is expected to produce, in order.

    Built from the script rather than from a hardcoded list because the script
    itself is generated per run (`build_rscmd`): `-mergeComponents`, `-save` and
    the COLMAP export are all switchable, and `rc.extra_align_commands` can add
    verbs the app does not model. An unknown verb is assumed to emit one task of
    average weight — wrong by a couple of percent if it emits none, which the id
    resync then corrects at the next known task.
    """
    plan: list[Task] = []
    for raw in script_text.splitlines():
        line = raw.strip()
        if not line.startswith("-"):
            continue
        verb = line[1:].split(None, 1)[0].strip('"')
        if not verb or verb in _SILENT_VERBS:
            continue
        plan.append(Task(verb, WEIGHTS.get(verb, _DEFAULT_WEIGHT)))
    return plan


def parse_line(line: str) -> Optional[tuple[int, float, float, str]]:
    """`(task id, fraction, remaining s, state)` — or None if it is not one.

    The elapsed clock is dropped: it is the one field of the line nothing
    downstream reads, and it is wrong on `#completed`.
    """
    match = _LINE.match(line.strip())
    if not match:
        return None
    task_id, fraction, _elapsed, remaining, state = match.groups()
    return int(task_id), float(fraction), float(remaining), state


class RCProgressTracker:
    """Folds RS's per-task lines into one monotone fraction for the step.

    Not thread-safe and not meant to be: it is fed from the single coroutine
    tailing the progress file.
    """

    def __init__(self, plan: list[Task]) -> None:
        self.plan = list(plan)
        self.cursor = -1          # index in `plan` of the task now running
        self.current_id: Optional[int] = None
        self._done_weight = 0.0
        self._highest = 0.0

    @property
    def _total(self) -> float:
        return sum(task.weight for task in self.plan) or 1.0

    def _advance(self, task_id: int) -> None:
        """Point the cursor at the plan entry this task id belongs to."""
        kind = KIND_BY_TASK_ID.get(task_id)
        target: Optional[int] = None
        if kind is not None:
            for index in range(self.cursor + 1, len(self.plan)):
                if self.plan[index].verb == kind:
                    target = index
                    break
        if target is None:
            target = self.cursor + 1

        # A task RS produced past the end of the plan: a verb we expected to be
        # silent was not, or `extra_align_commands` did something we did not
        # model. Grow the plan rather than divide by a total that excludes it.
        while target >= len(self.plan):
            self.plan.append(Task("unknown", _DEFAULT_WEIGHT))

        # Everything between the old cursor and the new one was skipped by RS —
        # credit it as done, which is what the file just told us.
        self._done_weight = sum(task.weight for task in self.plan[:target])
        self.cursor = target
        self.current_id = task_id

    def feed(self, line: str) -> Optional[Sample]:
        """One line in, one sample out — or None for a line that says nothing.

        The startup tasks are dropped rather than weighted: they are RS booting,
        they are the same three every run, and they are over before the script
        is read.
        """
        parsed = parse_line(line)
        if parsed is None:
            return None
        task_id, fraction, remaining, state = parsed
        if task_id in STARTUP_TASK_IDS:
            return None

        new_task = task_id != self.current_id
        if new_task:
            self._advance(task_id)

        task = self.plan[self.cursor]
        overall = (self._done_weight + task.weight * min(fraction, 1.0)) / self._total
        # Monotone by construction: a resync can only ever move the cursor
        # forward, but RS restarts the fraction at 0 for each task and a plan
        # entry that turns out lighter than the one before it would otherwise
        # step the bar backwards.
        self._highest = max(self._highest, min(overall, 0.99))

        return Sample(
            overall=self._highest,
            task=task,
            task_fraction=fraction,
            # `#completed` writes an estimate for a task that has just ended.
            remaining_s=None if state == "completed" else remaining,
            state=state,
            new_task=new_task,
        )
