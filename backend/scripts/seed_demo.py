"""Seed the database with demo devices and reference documents for presentations.

Usage:
    python -m backend.scripts.seed_demo

Requires a running PostgreSQL instance with the schema applied (alembic upgrade head).
"""
from __future__ import annotations

import asyncio
import uuid

from core.database import AsyncSessionLocal
from core.security import hash_password
from models.device import Device, DeviceAlarm, DeviceSpec, SerialCommand
from models.user import User


async def _seed() -> None:
    async with AsyncSessionLocal() as db:
        # --- Admin user ---
        admin = User(
            id=uuid.uuid4(),
            email="admin@docgen.demo",
            hashed_password=hash_password("admin123"),
            full_name="Demo Admin",
            role="admin",
            is_active=True,
        )
        db.add(admin)

        # --- Engineer user ---
        engineer = User(
            id=uuid.uuid4(),
            email="engineer@docgen.demo",
            hashed_password=hash_password("engineer123"),
            full_name="Demo Engineer",
            role="engineer",
            is_active=True,
        )
        db.add(engineer)

        # --- Device 1: VL8 Medical Laser ---
        vl8 = Device(
            id=uuid.uuid4(),
            name="VL8",
            model="VL8",
            document_code="15799",
            safety_class="B",
            driver_version="01",
            gui_version="7.0.0.7650",
        )
        db.add(vl8)
        db.add_all([
            DeviceSpec(device_id=vl8.id, category="laser", spec_key="wavelength_a", spec_value="808", spec_unit="nm"),
            DeviceSpec(device_id=vl8.id, category="laser", spec_key="wavelength_b", spec_value="1064", spec_unit="nm"),
            DeviceSpec(device_id=vl8.id, category="laser", spec_key="max_power", spec_value="8", spec_unit="W"),
            DeviceSpec(device_id=vl8.id, category="input", spec_key="switch_type", spec_value="Handswitch"),
            DeviceSpec(device_id=vl8.id, category="display", spec_key="screen_size", spec_value="7", spec_unit="inch"),
            DeviceSpec(device_id=vl8.id, category="display", spec_key="screen_type", spec_value="In-Cell ITF"),
            DeviceSpec(device_id=vl8.id, category="communication", spec_key="protocol", spec_value="RS-232"),
            DeviceSpec(device_id=vl8.id, category="communication", spec_key="baud_rate", spec_value="115200"),
            DeviceSpec(device_id=vl8.id, category="hardware", spec_key="gui_platform", spec_value="Raspberry Pi 3B+"),
            DeviceSpec(device_id=vl8.id, category="hardware", spec_key="driver_mcu", spec_value="STM32F207"),
            DeviceSpec(device_id=vl8.id, category="cooling", spec_key="cooling_type", spec_value="TEC + Fan"),
            DeviceSpec(device_id=vl8.id, category="battery", spec_key="battery_type", spec_value="Li-Ion Rechargeable"),
        ])
        db.add_all([
            DeviceAlarm(device_id=vl8.id, priority="High", condition="Laser temperature > 45°C", text_shown="Laser Overheat", indicator_light="Red", indicator_sound=True, required_action="Stop emission, wait for cooling", alarm_order=1),
            DeviceAlarm(device_id=vl8.id, priority="High", condition="Fiber not detected", text_shown="Fiber Error", indicator_light="Red", indicator_sound=True, required_action="Check fiber connection", alarm_order=2),
            DeviceAlarm(device_id=vl8.id, priority="Medium", condition="Battery < 10%", text_shown="Low Battery", indicator_light="Yellow", indicator_sound=False, required_action="Connect charger", alarm_order=3),
            DeviceAlarm(device_id=vl8.id, priority="Low", condition="Temperature sensor fault", text_shown="Sensor Fault", indicator_light="Yellow", indicator_sound=False, required_action="Service required", alarm_order=4),
        ])
        db.add_all([
            SerialCommand(device_id=vl8.id, direction="panel_to_main", command_name="START", description="Start laser emission", laser_a_mapping="0x01", laser_b_mapping="0x01", command_order=1),
            SerialCommand(device_id=vl8.id, direction="panel_to_main", command_name="STOP", description="Stop laser emission", laser_a_mapping="0x02", laser_b_mapping="0x02", command_order=2),
            SerialCommand(device_id=vl8.id, direction="panel_to_main", command_name="SET_POWER", description="Set power level", laser_a_mapping="0x03", laser_b_mapping="0x04", command_order=3),
            SerialCommand(device_id=vl8.id, direction="main_to_panel", command_name="SEND_STATUS", description="Send device status", laser_a_mapping="0x10", laser_b_mapping="0x10", command_order=4),
            SerialCommand(device_id=vl8.id, direction="main_to_panel", command_name="SEND_CALIBRATION", description="Send calibration data", laser_a_mapping="0x11", laser_b_mapping="0x12", command_order=5),
        ])

        # --- Device 2: DermaScan Ultra ---
        derma = Device(
            id=uuid.uuid4(),
            name="DermaScan Ultra",
            model="DSU-200",
            document_code="24801",
            safety_class="B",
            driver_version="02",
            gui_version="3.2.1",
        )
        db.add(derma)
        db.add_all([
            DeviceSpec(device_id=derma.id, category="laser", spec_key="wavelength_a", spec_value="755", spec_unit="nm"),
            DeviceSpec(device_id=derma.id, category="laser", spec_key="wavelength_b", spec_value="1064", spec_unit="nm"),
            DeviceSpec(device_id=derma.id, category="laser", spec_key="max_power", spec_value="15", spec_unit="W"),
            DeviceSpec(device_id=derma.id, category="input", spec_key="switch_type", spec_value="Footswitch"),
            DeviceSpec(device_id=derma.id, category="display", spec_key="screen_size", spec_value="10", spec_unit="inch"),
            DeviceSpec(device_id=derma.id, category="display", spec_key="screen_type", spec_value="Capacitive Touch"),
            DeviceSpec(device_id=derma.id, category="communication", spec_key="protocol", spec_value="RS-232"),
            DeviceSpec(device_id=derma.id, category="communication", spec_key="baud_rate", spec_value="115200"),
            DeviceSpec(device_id=derma.id, category="hardware", spec_key="gui_platform", spec_value="Raspberry Pi 4"),
            DeviceSpec(device_id=derma.id, category="hardware", spec_key="driver_mcu", spec_value="STM32F407"),
        ])

        await db.commit()
        print("Seeded: admin@docgen.demo / admin123")
        print("Seeded: engineer@docgen.demo / engineer123")
        print(f"Seeded device: VL8 (id={vl8.id})")
        print(f"Seeded device: DermaScan Ultra (id={derma.id})")


def main() -> None:
    asyncio.run(_seed())


if __name__ == "__main__":
    main()
