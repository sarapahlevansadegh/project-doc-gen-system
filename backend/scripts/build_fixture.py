"""Build a Dental Laser reference .docx fixture with real heading styles.

This lets the extraction/splitting pipeline be exercised on a structured
Word document rather than a flat text blob. Content mirrors the existing
reference document sections.
"""
from pathlib import Path

from docx import Document

SECTIONS = [
    ("1. Architecture of Software", 1, [
        "Figure 1 - General interfaces with the device. According to figure 1, "
        "interaction control logic defines the procedures through which the user "
        "interacts with the device, coordinates with the control software to "
        "respond to user inputs, and determines the content and timing of "
        "information and feedback presented to the user.",
    ]),
    ("1.1 LCD Module", 2, [
        "The GUI software generates the data to be displayed on the LCD, which "
        "can include text, images, icons, and other graphical elements. The user "
        "can view and interact with the information presented on the screen.",
    ]),
    ("1.2 Sound Module", 2, [
        "The GUI software processes the user input data to determine the desired "
        "volume levels for the touch and buzzer functionalities and sends the "
        "corresponding data to the sound module.",
    ]),
    ("1.3 Wi-Fi Module", 2, [
        "The GUI software communicates with a remote server to determine if any "
        "updates are available for the device and manages the transfer of the "
        "update package via the Wi-Fi module.",
    ]),
    ("1.4 Storage and Battery", 2, [
        "A storage flash memory is used to save therapeutic protocols, placement "
        "images, error messages and other user settings. The microcontroller "
        "monitors battery voltage using the ADC and generates a low battery "
        "warning when thresholds are crossed.",
    ]),
    ("1.5 Sensors and Input Devices", 2, [
        "Temperature sensors measure laser diode and battery temperature. The "
        "fiber sensor recognizes if the optic fiber is not connected. The "
        "footswitch state is controlled by the microcontroller.",
    ]),
    ("1.6 LED and Cooling System", 2, [
        "The dental laser device includes an LED indicating the status of the "
        "laser radiation module with four modes: off, standby, ready, and "
        "emitting. The cooling system including TEC and Fan is controlled by the "
        "microcontroller.",
    ]),
    ("1.7 Interlock and Laser Module", 2, [
        "The driver software constantly monitors the status of the interlock "
        "key. The laser module is equipped with a laser driver circuit that "
        "provides the necessary electrical power and control signals.",
    ]),
    ("2. Serial Communication Architecture", 1, [
        "There is a serial communication protocol (RS-232) between GUI software "
        "and Driver software at baudrate 115200, little-endian, with an XOR "
        "checksum. ACK command byte is 0xaaaa.",
    ]),
    ("3. Software Architecture Verification", 1, [
        "The software architecture is verified by technical evaluation to ensure "
        "all software requirements can be implemented by the identified software "
        "items.",
    ]),
    ("5. SOUP Functional Requirements", 1, [
        "The GUI software depends on the Linux operating system and supporting "
        "libraries. The driver software has no generally available SOUP items.",
    ]),
    ("6. Hardware and Software Requirements", 1, [
        "GUI hardware: Quad-core 64-bit Broadcom BCM2837 ARM Cortex-A53, 1GB RAM, "
        "Vertical ITF touch display, MicroSD, 802.11n Wi-Fi. Software: Custom "
        "Debian base OS, Qt 5.12.11, GCC.",
    ]),
    ("7. Software Specifications", 1, [
        "Driver Software: Keil, C++, Keil Compiler, STM32F207/217. GUI Software: "
        "QT Creator, C++ and QML, QT 5.12.11, GCC, Linux, Raspberry Pi 3B+.",
    ]),
]


def build_fixture(out_path: str | Path) -> Path:
    out_path = Path(out_path)
    doc = Document()
    doc.add_heading("Software Architectural Design", level=0)
    doc.add_paragraph("Device Name: Dental Laser   Software Safety Class: B")

    for title, level, paras in SECTIONS:
        doc.add_heading(title, level=level)
        for p in paras:
            doc.add_paragraph(p)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
    return out_path


if __name__ == "__main__":
    target = Path(__file__).parent.parent.parent / "reference_templates" / "dental_laser_reference.docx"
    print("wrote", build_fixture(target))
