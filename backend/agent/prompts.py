"""Prompts for section generation."""
from __future__ import annotations


def build_section_prompt(
    section_name: str,
    reference_content: str,
    device_data: dict,
    similar_context: list[str] | None = None,
) -> str:
    """Build the prompt for generating one document section.

    Includes:
      - the reference section content (structure/tone to follow)
      - the new device specifications
      - an instruction to preserve the engineering/regulatory style
    """
    similar = "\n\n".join(similar_context or [])

    device_specs = device_data.get("specs", {})
    specs_text = "\n".join(f"  - {k}: {v}" for k, v in device_specs.items()) or "  (none provided)"

    alarms = device_data.get("alarms", [])
    alarms_text = (
        "\n".join(
            f"  - [{a.get('priority', '?')}] {a.get('condition', '')}"
            for a in alarms
        )
        or "  (none)"
    )

    commands = device_data.get("commands", [])
    commands_text = (
        "\n".join(f"  - {c.get('name', c.get('command_name', ''))}" for c in commands)
        or "  (none)"
    )

    return f"""You are an expert medical device software documentation engineer.

Generate the '{section_name}' section for a Software Architectural Design document.

# NEW DEVICE INFORMATION
Name: {device_data.get('name')}
Model: {device_data.get('model')}
Document Code: {device_data.get('document_code')}
Safety Class: {device_data.get('safety_class')}
Driver Version: {device_data.get('driver_version')}
GUI Version: {device_data.get('gui_version')}

Specifications:
{specs_text}

Alarms:
{alarms_text}

Serial Commands:
{commands_text}

# REFERENCE SECTION (preserve its structure, headings and professional tone)
{reference_content}

# SIMILAR REFERENCE SECTIONS (additional context)
{similar or '(none)'}

# INSTRUCTIONS
- Follow the exact structure, numbering, and professional engineering tone of the reference section.
- Replace all device-specific details (wavelengths, power, switch type, modules, commands) with the NEW device's values above.
- Keep all IEC 62304 / regulatory compliance language intact.
- Be technically accurate and internally consistent with the device information.
- Use formal English throughout.
- Only use specifications provided in the device information; do not invent technical specs.
- Do not include phrases such as "Here is the generated section".
- Generate only the final content of the '{section_name}' section.
""".strip()
