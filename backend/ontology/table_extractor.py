"""Rule-based (no LLM) extraction of Specification entities from chunk text.

Why this exists: asking an LLM to read a whole table chunk returns only a few
rows and the result changes from run to run. Table rows in the input documents
are regular enough to read with plain rules, so every parameter row and every
alarm row becomes one Specification entity, the same way every time.

Output format, chosen so services/document_diff_planner._specification_key
(text before the first ":" is the key) gives each fact its own key:

    parameter table row  ->  "<Parameter> <Column>: <cell>"
                              e.g. "Duty Cycle (%) Range: 1-95"
    alarm table row      ->  "<Condition>: <column> <cell>; <column> <cell>; ..."
                              e.g. "Laser module over temperature: priority High; limit 45º; ..."
    plain text line      ->  "<Name>: <rest of the line>"
                              e.g. "Frequency: 1Hz to 100KHz"

Long tables are split into several chunks and the later chunks have no header
row. The header of the last table is therefore returned to the caller, which
passes it back in for the next chunk of the same document.

Nothing here is guessed: a table whose header is not recognised yields nothing.
"""
from __future__ import annotations

import re

from ontology.validator import Entity, validate_entity

SPECIFICATION = "Specification"
MAX_VALUE_LEN = 500  # ontology_entities.value is String(500)

_EMPTY_CELLS = {"", "-", "\u2013", "\u2014"}
_NUMBER_COLUMNS = {"no", "no.", "#", "row", "number"}
_SEPARATOR_CELL = re.compile(r":?-{3,}:?")
_LINE = re.compile(r"^(?P<name>[^:|]{2,80}?)\s*:\s*(?P<value>\S.*)$")
_BULLET = re.compile(r"^\s*[-\u2022*]\s+")
_SKIP_FIRST_WORDS = {"note", "notes", "caution", "warning", "example", "figure", "table", "intro"}
# Two facts glued on one line: "... duration. Frequency: It should ..."
_FACT_BREAK = re.compile(r"(?<=[.!?])\s+(?=[A-Z][A-Za-z /()\-]{1,40}:\s)")


def _split_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [cell.strip() for cell in line.split("|")]


def _is_separator(cells: list[str]) -> bool:
    return bool(cells) and all(_SEPARATOR_CELL.fullmatch(c) for c in cells)


def _classify(header: list[str]) -> tuple[str, int] | None:
    """Return ("alarm"|"param", column index) for a header we understand."""
    low = [c.lower() for c in header]
    for i, cell in enumerate(low):
        # "Alarm/Warning Condition", not a section title such as "Operating conditions"
        if "condition" in cell and ("alarm" in cell or "warning" in cell):
            return "alarm", i
    for i, cell in enumerate(low):
        if "parameter" in cell or "setting" in cell:
            return "param", i
    return None


def _is_number_column(title: str) -> bool:
    return title.strip().lower() in _NUMBER_COLUMNS


def _make(value: str) -> Entity | None:
    value = " ".join(value.split())[:MAX_VALUE_LEN]
    if not value:
        return None
    entity = Entity(type=SPECIFICATION, value=value)
    return entity if validate_entity(entity).valid else None


def _param_row(header: list[str], idx: int, row: list[str]) -> list[str]:
    if idx >= len(row):
        return []
    name = row[idx].replace(":", " ").strip()
    if not name or name.lower() in _EMPTY_CELLS or _is_number_column(name):
        return []
    out = []
    for j, cell in enumerate(row):
        if j == idx or j >= len(header) or _is_number_column(header[j]):
            continue
        if cell.strip() in _EMPTY_CELLS:
            continue
        title = header[j].strip()
        out.append(f"{name} {title}: {cell}" if title else f"{name}: {cell}")
    return out


def _alarm_row(header: list[str], idx: int, row: list[str]) -> list[str]:
    if idx >= len(row):
        return []
    condition = row[idx].strip().rstrip(".").replace(":", " ").strip()
    if not condition or condition.lower() in _EMPTY_CELLS:
        return []
    parts = []
    for j, cell in enumerate(row):
        if j == idx or j >= len(header) or _is_number_column(header[j]):
            continue
        if cell.strip() in _EMPTY_CELLS:
            continue
        parts.append(f"{header[j].strip().lower()} {cell}".strip())
    return [f"{condition}: {'; '.join(parts)}"] if parts else []


def _section_rows(header: list[str], data: list[list[str]]) -> list[str]:
    """Two-column "label | value" tables under a title row such as
    "Operating conditions". The title (and any later row whose two cells are
    the same text, e.g. "Transport and storage conditions") is put in front of
    the label so that "Ambient temperature" in two sections gets two keys."""
    if len(header) != 2 or header[1] not in ("", header[0]):
        return []
    section = header[0].strip()
    if len(section.split()) < 2 or not re.search(r"[A-Za-z]", section):
        return []
    values = []
    for row in data:
        if len(row) != 2 or _is_separator(row):
            continue
        label, value = row[0].strip(), row[1].strip()
        if label and label == value:
            section = label
        elif label and value not in _EMPTY_CELLS and label.lower() not in _EMPTY_CELLS:
            values.append(f"{section} {label.replace(':', ' ')}: {value}")
    return values


def _table_values(block: list[str], carried: list[str] | None) -> tuple[list[str], list[str] | None]:
    rows = [_split_row(line) for line in block]
    sep = next((i for i, r in enumerate(rows) if _is_separator(r)), None)

    if sep is not None and sep >= 1:
        header = rows[sep - 1]
        data = rows[sep + 1:]
        # A title row ("Game's Parameters") can sit above the real header row.
        if data and len(header) != len(data[0]) and _classify(data[0]):
            header, data = data[0], data[1:]
        new_carried = header
    elif carried and rows and len(carried) == len(rows[0]):
        header, data, new_carried = carried, rows, carried
    else:
        return [], carried

    kind = _classify(header)
    if kind is None:
        return _section_rows(header, data), new_carried
    mode, idx = kind
    build = _alarm_row if mode == "alarm" else _param_row
    values: list[str] = []
    for row in data:
        if _is_separator(row):
            continue
        values.extend(build(header, idx, row))
    return values, new_carried


def _line_value(line: str) -> str | None:
    text = _BULLET.sub("", line).strip()
    match = _LINE.match(text)
    if not match:
        return None
    name, value = match.group("name").strip(), match.group("value").strip()
    words = name.split()
    if not words or len(words) > 8 or words[0].lower().rstrip(".") in _SKIP_FIRST_WORDS:
        return None
    return f"{name}: {value}"


def extract_rule_based_entities(
    chunk_text: str, carried_header: list[str] | None = None
) -> tuple[list[Entity], list[str] | None]:
    """Return (entities, header to carry into the next chunk of this document)."""
    if not chunk_text or not chunk_text.strip():
        return [], carried_header

    values: list[str] = []
    block: list[str] = []
    carried = carried_header

    def flush() -> None:
        nonlocal block, carried
        if block:
            table_values, carried = _table_values(block, carried)
            values.extend(table_values)
            block = []

    for line in chunk_text.splitlines():
        if line.strip().startswith("|"):
            block.append(line)
            continue
        flush()
        for fact in _FACT_BREAK.split(line):
            value = _line_value(fact)
            if value:
                values.append(value)
    flush()

    entities: list[Entity] = []
    seen: set[str] = set()
    for value in values:
        entity = _make(value)
        if entity and entity.value not in seen:
            seen.add(entity.value)
            entities.append(entity)
    return entities, carried
