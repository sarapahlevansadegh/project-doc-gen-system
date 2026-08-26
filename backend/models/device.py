import uuid
from datetime import datetime

from core.database import Base
from models.device_document import DeviceDocument
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=True)
    document_code: Mapped[str] = mapped_column(String(50), nullable=True)
    safety_class: Mapped[str] = mapped_column(String(10), default="B")
    driver_version: Mapped[str] = mapped_column(String(50), nullable=True)
    gui_version: Mapped[str] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    specs: Mapped[list["DeviceSpec"]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )
    alarms: Mapped[list["DeviceAlarm"]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )
    commands: Mapped[list["SerialCommand"]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )
    documents: Mapped[list["DeviceDocument"]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )


class DeviceSpec(Base):
    __tablename__ = "device_specs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    spec_key: Mapped[str] = mapped_column(String(255), nullable=False)
    spec_value: Mapped[str] = mapped_column(Text, nullable=False)
    spec_unit: Mapped[str] = mapped_column(String(50), nullable=True)

    device: Mapped["Device"] = relationship(back_populates="specs")


class DeviceAlarm(Base):
    __tablename__ = "device_alarms"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id"), nullable=False
    )
    priority: Mapped[str] = mapped_column(String(20), nullable=True)
    condition: Mapped[str] = mapped_column(Text, nullable=False)
    text_shown: Mapped[str] = mapped_column(Text, nullable=True)
    indicator_light: Mapped[str] = mapped_column(String(100), nullable=True)
    indicator_sound: Mapped[bool] = mapped_column(Boolean, default=False)
    required_action: Mapped[str] = mapped_column(Text, nullable=True)
    alarm_order: Mapped[int] = mapped_column(Integer, nullable=True)

    device: Mapped["Device"] = relationship(back_populates="alarms")


class SerialCommand(Base):
    __tablename__ = "serial_commands"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id"), nullable=False
    )
    direction: Mapped[str] = mapped_column(String(20), nullable=True)
    command_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    laser_a_mapping: Mapped[str] = mapped_column(String(100), nullable=True)
    laser_b_mapping: Mapped[str] = mapped_column(String(100), nullable=True)
    command_order: Mapped[int] = mapped_column(Integer, nullable=True)

    device: Mapped["Device"] = relationship(back_populates="commands")
