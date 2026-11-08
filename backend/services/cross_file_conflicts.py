"""Compare what different input files say about the same parameter.

Database-free: the caller passes in (value, input_type) pairs and gets back a
list of findings. Nothing here decides which value is right; every finding is
for an engineer to review.

Three kinds of finding:

* cross_file     the same parameter has values in two input files and the
                 values cannot all be true at once.
* within_file    one file gives two incompatible values under the same label
                 (often two different sections, e.g. operating and storage
                 temperature, so it is reported separately and not as a
                 conflict between files).
* unpaired_alarm an alarm row that exists in one file and has no row with the
                 same condition in another file that also lists alarms.

How two values are compared (no LLM): each value is reduced to the set of
numbers it contains, after unit scaling (1K and 1 kHz are 1000, 0.2 W is 200
and 50 mW is 50). Two values agree when one number set contains the other, so
"0-8W ... 0.2W for 650nm" does not contradict "8 watts". A value without any
number cannot be compared and is skipped. Alarm rows are compared on priority,
required action and the number in the limit (or in the condition's brackets).

Names are matched after removing bracketed units, a leading "the"/"a", and a
trailing "range"/"limit" ("Duty Cycle (%) Range" and "Duty cycle" are the same
parameter). Names that only mean the same thing in other words ("Low Battery"
and "The battery charge drops below 20%") are not paired here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import combinations

from services.conflict_benchmark import Inconsistency

CROSS_FILE = "cross_file"
WITHIN_FILE = "within_file"
UNPAIRED_ALARM = "unpaired_alarm"

_NUMBER = re.compile(
    r"(?<![A-Za-z0-9.])(\d+(?:\.\d+)?)(?:\s*(mw|khz|k|watts?|w)(?![A-Za-z]))?",
    re.IGNORECASE,
)
_ALARM_FIELDS = (
    "priority",
    "limit",
    "text to be shown",
    "indicator light",
    "indicator sound",
    "required action",
)


@dataclass(frozen=True)
class SourcedValue:
    value: str
    input_type: str


@dataclass(frozen=True)
class Finding:
    kind: str
    key: str
    values: tuple[tuple[str, str], ...]  # (input_type, original value)
    note: str

    def to_inconsistency(self) -> Inconsistency:
        return Inconsistency(self.key, tuple(v for _, v in self.values))


def normalize_name(name: str) -> str:
    name = re.sub(r"\([^)]*\)", " ", name.lower())
    name = re.sub(r"[^\w/\- ]+", " ", name)
    name = " ".join(name.split())
    name = re.sub(r"^(the|a|an) ", "", name)
    name = re.sub(r"\b(ranges|range|limits|limit)$", "", name).strip()
    name = re.sub(r"\bsteps$", "step", name)
    name = re.sub(r"\bdefault value( ?/ ?setting)?$", "default", name)
    return name


def number_signature(text: str) -> frozenset[str]:
    numbers = set()
    for match in _NUMBER.finditer(text):
        value = float(match.group(1))
        unit = (match.group(2) or "").lower()
        if unit in ("k", "khz") or unit.startswith("watt") or unit == "w":
            value *= 1000
        numbers.add(format(value, "g"))
    return frozenset(numbers)


def _compatible(a: frozenset[str], b: frozenset[str]) -> bool | None:
    if not a or not b:
        return None
    return a <= b or b <= a


def _split(value: str) -> tuple[str, str] | None:
    if ":" not in value:
        return None
    name, rest = value.split(":", 1)
    return name.strip(), rest.strip()


def _is_alarm(rest: str) -> bool:
    return rest.lower().startswith("priority ")


def _alarm_fields(rest: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for part in rest.split("; "):
        lowered = part.lower()
        for field in _ALARM_FIELDS:
            if lowered.startswith(field + " "):
                fields[field] = part[len(field):].strip()
                break
    return fields


def _flat(text: str) -> str:
    return re.sub(r"\s+", "", text).rstrip(".").lower()


def _alarm_difference(a_name: str, a: dict[str, str], b_name: str, b: dict[str, str]) -> str | None:
    for field in ("priority", "required action"):
        if field in a and field in b and _flat(a[field]) != _flat(b[field]):
            return f"{field}: {a[field]} / {b[field]}"
    a_numbers = number_signature(" ".join(re.findall(r"\(([^)]*)\)", a_name)) + " " + a.get("limit", ""))
    b_numbers = number_signature(" ".join(re.findall(r"\(([^)]*)\)", b_name)) + " " + b.get("limit", ""))
    if _compatible(a_numbers, b_numbers) is False:
        return f"limit: {sorted(a_numbers)} / {sorted(b_numbers)}"
    return None


def find_conflicts(items: list[SourcedValue]) -> list[Finding]:
    specs: dict[str, dict[str, list[tuple[str, frozenset[str]]]]] = {}
    alarms: dict[str, dict[str, list[tuple[str, str, dict[str, str]]]]] = {}

    for item in items:
        parts = _split(item.value)
        if parts is None:
            continue
        name, rest = parts
        key = normalize_name(name)
        if len(key) < 3 or not re.search(r"[a-z]", key):
            continue
        if _is_alarm(rest):
            alarms.setdefault(key, {}).setdefault(item.input_type, []).append(
                (item.value, name, _alarm_fields(rest))
            )
        else:
            specs.setdefault(key, {}).setdefault(item.input_type, []).append(
                (item.value, number_signature(rest))
            )

    findings: list[Finding] = []

    for key, by_file in sorted(specs.items()):
        for file_a, file_b in combinations(sorted(by_file), 2):
            outcomes = [
                _compatible(sig_a, sig_b)
                for _, sig_a in by_file[file_a]
                for _, sig_b in by_file[file_b]
            ]
            comparable = [o for o in outcomes if o is not None]
            if comparable and not any(comparable):
                values = tuple((file_a, v) for v, _ in by_file[file_a]) + tuple(
                    (file_b, v) for v, _ in by_file[file_b]
                )
                findings.append(Finding(CROSS_FILE, key, values, f"{file_a} and {file_b} disagree"))
        for file, entries in sorted(by_file.items()):
            sigs = [s for _, s in entries if s]
            if any(_compatible(a, b) is False for a, b in combinations(sigs, 2)):
                values = tuple((file, v) for v, _ in entries)
                findings.append(
                    Finding(WITHIN_FILE, key, values,
                            f"{file} gives different values under one label (maybe different sections)")
                )

    for key, by_file in sorted(alarms.items()):
        for file_a, file_b in combinations(sorted(by_file), 2):
            for raw_a, name_a, fields_a in by_file[file_a]:
                for raw_b, name_b, fields_b in by_file[file_b]:
                    difference = _alarm_difference(name_a, fields_a, name_b, fields_b)
                    if difference:
                        findings.append(
                            Finding(CROSS_FILE, key, ((file_a, raw_a), (file_b, raw_b)),
                                    f"alarm differs in {difference}")
                        )

    files_with_alarms = sorted({f for by_file in alarms.values() for f in by_file})
    for file_a, file_b in combinations(files_with_alarms, 2):
        for key, by_file in sorted(alarms.items()):
            for present, missing in ((file_a, file_b), (file_b, file_a)):
                if present in by_file and missing not in by_file:
                    findings.append(
                        Finding(UNPAIRED_ALARM, key,
                                tuple((present, raw) for raw, _, _ in by_file[present]),
                                f"in {present}, no alarm with this condition in {missing}")
                    )
    return findings
