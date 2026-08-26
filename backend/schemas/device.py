"""Pydantic schemas for device input/management."""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SafetyClass(str, Enum):
    A = "A"
    B = "B"
    C = "C"


class CommandDirection(str, Enum):
    PANEL_TO_MAIN = "panel_to_main"
    MAIN_TO_PANEL = "main_to_panel"


class AlarmPriority(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class DeviceSpecIn(BaseModel):
    category: str = Field(..., min_length=1)
    spec_key: str = Field(..., min_length=1)
    spec_value: str = Field(..., min_length=1)
    spec_unit: str | None = None
    # optional numeric value used for positive-value validation
    numeric_value: float | None = Field(default=None, ge=0)

    model_config = ConfigDict(extra="forbid")


class DeviceAlarmIn(BaseModel):
    priority: AlarmPriority | None = None
    condition: str = Field(..., min_length=1)
    text_shown: str | None = None
    indicator_light: str | None = None
    indicator_sound: bool = False
    required_action: str | None = None
    alarm_order: int | None = None

    model_config = ConfigDict(extra="forbid")


class SerialCommandIn(BaseModel):
    direction: CommandDirection | None = None
    command_name: str = Field(..., min_length=1)
    description: str | None = None
    laser_a_mapping: str | None = None
    laser_b_mapping: str | None = None
    command_order: int | None = None

    model_config = ConfigDict(extra="forbid")


class DeviceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    model: str | None = Field(default=None, max_length=100)
    document_code: str | None = Field(default=None, max_length=50)
    safety_class: SafetyClass = SafetyClass.B
    driver_version: str | None = Field(default=None, max_length=50)
    gui_version: str | None = Field(default=None, max_length=50)
    specs: list[DeviceSpecIn] = Field(default_factory=list)
    alarms: list[DeviceAlarmIn] = Field(default_factory=list)
    commands: list[SerialCommandIn] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @field_validator("specs")
    @classmethod
    def _specs_not_empty_for_generation(cls, v):
        # Allow empty, but if provided each must be valid (handled per-item).
        return v


class DeviceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    model: str | None = Field(default=None, max_length=100)
    document_code: str | None = Field(default=None, max_length=50)
    safety_class: SafetyClass | None = None
    driver_version: str | None = Field(default=None, max_length=50)
    gui_version: str | None = Field(default=None, max_length=50)
    specs: list[DeviceSpecIn] | None = None
    alarms: list[DeviceAlarmIn] | None = None
    commands: list[SerialCommandIn] | None = None

    model_config = ConfigDict(extra="forbid")


class DeviceSpecOut(BaseModel):
    id: uuid.UUID
    category: str
    spec_key: str
    spec_value: str
    spec_unit: str | None

    model_config = ConfigDict(from_attributes=True)


class DeviceAlarmOut(BaseModel):
    id: uuid.UUID
    priority: str | None
    condition: str
    text_shown: str | None
    indicator_light: str | None
    indicator_sound: bool
    required_action: str | None
    alarm_order: int | None

    model_config = ConfigDict(from_attributes=True)


class SerialCommandOut(BaseModel):
    id: uuid.UUID
    direction: str | None
    command_name: str
    description: str | None
    laser_a_mapping: str | None
    laser_b_mapping: str | None
    command_order: int | None

    model_config = ConfigDict(from_attributes=True)


class DeviceDocumentOut(BaseModel):
    id: uuid.UUID
    device_id: uuid.UUID
    filename: str
    file_size: int
    content_type: str | None
    created_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class DeviceOut(BaseModel):
    id: uuid.UUID
    name: str
    model: str | None
    document_code: str | None
    safety_class: str
    driver_version: str | None
    gui_version: str | None
    created_at: datetime | None
    specs: list[DeviceSpecOut] = []
    alarms: list[DeviceAlarmOut] = []
    commands: list[SerialCommandOut] = []
    documents: list[DeviceDocumentOut] = []

    model_config = ConfigDict(from_attributes=True)
