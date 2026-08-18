"""Device service layer (business logic for device management)."""
from __future__ import annotations

import uuid

from models.device import Device, DeviceAlarm, DeviceSpec, SerialCommand
from schemas.device import DeviceAlarmIn, DeviceCreate, DeviceSpecIn, DeviceUpdate, SerialCommandIn
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


def _build_specs(device_id: uuid.UUID, specs):
    return [
        DeviceSpec(
            device_id=device_id,
            category=s.category,
            spec_key=s.spec_key,
            spec_value=s.spec_value,
            spec_unit=s.spec_unit,
        )
        for s in specs
    ]


def _build_alarms(device_id: uuid.UUID, alarms):
    return [
        DeviceAlarm(
            device_id=device_id,
            priority=a.priority.value if a.priority else None,
            condition=a.condition,
            text_shown=a.text_shown,
            indicator_light=a.indicator_light,
            indicator_sound=a.indicator_sound,
            required_action=a.required_action,
            alarm_order=a.alarm_order,
        )
        for a in alarms
    ]


def _build_commands(device_id: uuid.UUID, commands):
    return [
        SerialCommand(
            device_id=device_id,
            direction=c.direction.value if c.direction else None,
            command_name=c.command_name,
            description=c.description,
            laser_a_mapping=c.laser_a_mapping,
            laser_b_mapping=c.laser_b_mapping,
            command_order=c.command_order,
        )
        for c in commands
    ]


async def create_device(db: AsyncSession, payload: DeviceCreate) -> Device:
    device = Device(
        name=payload.name,
        model=payload.model,
        document_code=payload.document_code,
        safety_class=payload.safety_class.value,
        driver_version=payload.driver_version,
        gui_version=payload.gui_version,
    )
    db.add(device)
    await db.flush()  # populate device.id

    db.add_all(_build_specs(device.id, payload.specs))
    db.add_all(_build_alarms(device.id, payload.alarms))
    db.add_all(_build_commands(device.id, payload.commands))

    await db.commit()
    result = await db.execute(
        select(Device)
        .where(Device.id == device.id)
        .options(
            selectinload(Device.specs),
            selectinload(Device.alarms),
            selectinload(Device.commands),
        )
    )
    return result.scalar_one()


async def list_devices(
    db: AsyncSession, skip: int = 0, limit: int = 50, search: str | None = None
) -> dict:
    query = select(Device)
    count_query = select(func.count()).select_from(Device)
    if search:
        pattern = f"%{search}%"
        query = query.where(
            or_(Device.name.ilike(pattern), Device.model.ilike(pattern))
        )
        count_query = count_query.where(
            or_(Device.name.ilike(pattern), Device.model.ilike(pattern))
        )
    total = await db.scalar(count_query) or 0
    result = await db.execute(
        query.order_by(Device.created_at.desc())
        .offset(skip)
        .limit(limit)
        .options(
            selectinload(Device.specs),
            selectinload(Device.alarms),
            selectinload(Device.commands),
        )
    )
    return {"items": list(result.scalars().all()), "total": total, "skip": skip, "limit": limit}


async def get_device(db: AsyncSession, device_id: str) -> Device | None:
    try:
        uid = uuid.UUID(device_id)
    except ValueError:
        return None
    result = await db.execute(
        select(Device)
        .where(Device.id == uid)
        .options(
            selectinload(Device.specs),
            selectinload(Device.alarms),
            selectinload(Device.commands),
        )
    )
    return result.scalar_one_or_none()


async def update_device(
    db: AsyncSession, device: Device, payload: DeviceUpdate
) -> Device:
    data = payload.model_dump(exclude_unset=True)
    if "safety_class" in data and data["safety_class"] is not None:
        data["safety_class"] = data["safety_class"].value

    scalar_keys = {"name", "model", "document_code", "safety_class",
                   "driver_version", "gui_version"}
    for key in scalar_keys:
        if key in data:
            setattr(device, key, data[key])

    if data.get("specs") is not None:
        await _replace_children(db, device, "specs", data["specs"], _build_specs, DeviceSpecIn)
    if data.get("alarms") is not None:
        await _replace_children(db, device, "alarms", data["alarms"], _build_alarms, DeviceAlarmIn)
    if data.get("commands") is not None:
        await _replace_children(db, device, "commands", data["commands"], _build_commands, SerialCommandIn)

    await db.commit()
    result = await db.execute(
        select(Device)
        .where(Device.id == device.id)
        .options(
            selectinload(Device.specs),
            selectinload(Device.alarms),
            selectinload(Device.commands),
        )
    )
    return result.scalar_one()


async def _replace_children(db, device, attr, items, builder, item_schema):
    """Delete existing child rows for a device and re-add from payload.

    Relies on the ORM cascade/delete-orphan configured on the relationship so
    removing items from the collection deletes the child rows. Items may arrive
    as dicts (PATCH body) and are validated through ``item_schema`` first.
    """
    validated = [item if isinstance(item, item_schema) else item_schema(**item)
                 for item in items]
    existing = getattr(device, attr)
    for child in list(existing):
        existing.remove(child)
    for built in builder(device.id, validated):
        existing.append(built)


async def delete_device(db: AsyncSession, device: Device) -> None:
    from models.document import GeneratedDocument
    from sqlalchemy import delete as sa_delete

    await db.execute(
        sa_delete(GeneratedDocument).where(GeneratedDocument.device_id == device.id)
    )
    await db.delete(device)
    await db.commit()


async def get_device_data(db: AsyncSession, device_id: str) -> dict:
    """Load full device information (specs, alarms, commands) as a dict."""
    device = await get_device(db, device_id)
    if device is None:
        raise ValueError(f"Device {device_id} not found")

    specs_result = await db.execute(
        select(DeviceSpec).where(DeviceSpec.device_id == device_id)
    )
    specs = specs_result.scalars().all()

    alarms_result = await db.execute(
        select(DeviceAlarm)
        .where(DeviceAlarm.device_id == device_id)
        .order_by(DeviceAlarm.alarm_order)
    )
    alarms = alarms_result.scalars().all()

    commands_result = await db.execute(
        select(SerialCommand)
        .where(SerialCommand.device_id == device_id)
        .order_by(SerialCommand.command_order)
    )
    commands = commands_result.scalars().all()

    return {
        "name": device.name,
        "model": device.model,
        "document_code": device.document_code,
        "safety_class": device.safety_class,
        "driver_version": device.driver_version,
        "gui_version": device.gui_version,
        "specs": {s.spec_key: s.spec_value for s in specs},
        "alarms": [
            {
                "priority": a.priority,
                "condition": a.condition,
                "text_shown": a.text_shown,
                "indicator_light": a.indicator_light,
                "indicator_sound": a.indicator_sound,
                "required_action": a.required_action,
                "order": a.alarm_order,
            }
            for a in alarms
        ],
        "commands": [
            {
                "direction": c.direction,
                "name": c.command_name,
                "description": c.description,
                "laser_a": c.laser_a_mapping,
                "laser_b": c.laser_b_mapping,
                "order": c.command_order,
            }
            for c in commands
        ],
    }
