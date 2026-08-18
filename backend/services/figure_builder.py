import uuid
from pathlib import Path

import cairosvg


def generate_figure1(device_data: dict) -> bytes:
    """Figure 1 — General interfaces with the device"""
    name = device_data.get("name", "Device")
    switch_type = device_data.get("specs", {}).get("switch_type", "Footswitch")
    wav_a = device_data.get("specs", {}).get("wavelength_a", "")
    wav_b = device_data.get("specs", {}).get("wavelength_b", "")
    max_power = device_data.get("specs", {}).get("max_power", "")
    laser_label = f"{wav_a} nm · {wav_b} nm · {max_power} W" if wav_a else name

    svg = f'''<svg width="700" height="540" xmlns="http://www.w3.org/2000/svg">
<rect width="700" height="540" fill="white"/>
<defs>
  <marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
    <path d="M0 1.5L9 5L0 8.5Z" fill="#1F4E79"/>
  </marker>
  <marker id="arr2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
    <path d="M0 1.5L9 5L0 8.5Z" fill="#0F6E56"/>
  </marker>
</defs>
<rect x="225" y="20" width="250" height="48" rx="8" fill="#1F4E79"/>
<text x="350" y="40" text-anchor="middle" font-family="Arial" font-size="13" font-weight="bold" fill="white">User</text>
<text x="350" y="58" text-anchor="middle" font-family="Arial" font-size="11" fill="#B5D4F4">Physiotherapist / Operator</text>
<line x1="350" y1="68" x2="350" y2="96" stroke="#1F4E79" stroke-width="2" marker-end="url(#arr)"/>
<line x1="340" y1="96" x2="340" y2="68" stroke="#1F4E79" stroke-width="2" marker-end="url(#arr)"/>
<rect x="130" y="98" width="440" height="50" rx="8" fill="#2E75B6"/>
<text x="350" y="120" text-anchor="middle" font-family="Arial" font-size="13" font-weight="bold" fill="white">Interaction Control Logic</text>
<text x="350" y="138" text-anchor="middle" font-family="Arial" font-size="11" fill="#D6E8F8">Coordinates user inputs · Controls feedback timing</text>
<line x1="240" y1="148" x2="180" y2="180" stroke="#1F4E79" stroke-width="1.8" marker-end="url(#arr)"/>
<line x1="460" y1="148" x2="520" y2="180" stroke="#1F4E79" stroke-width="1.8" marker-end="url(#arr)"/>
<rect x="30" y="182" width="300" height="50" rx="8" fill="#E6F1FB" stroke="#2E75B6" stroke-width="1.5"/>
<text x="180" y="203" text-anchor="middle" font-family="Arial" font-size="12" font-weight="bold" fill="#1F4E79">Input Interpreter</text>
<text x="180" y="221" text-anchor="middle" font-family="Arial" font-size="10" fill="#2E75B6">Touch · {switch_type} · Long-press</text>
<rect x="370" y="182" width="300" height="50" rx="8" fill="#E6F1FB" stroke="#2E75B6" stroke-width="1.5"/>
<text x="520" y="203" text-anchor="middle" font-family="Arial" font-size="12" font-weight="bold" fill="#1F4E79">Output Render</text>
<text x="520" y="221" text-anchor="middle" font-family="Arial" font-size="10" fill="#2E75B6">Screen Layout · Sound · LED Feedback</text>
<line x1="90" y1="232" x2="70" y2="270" stroke="#2E75B6" stroke-width="1.5" marker-end="url(#arr)"/>
<line x1="180" y1="232" x2="180" y2="270" stroke="#2E75B6" stroke-width="1.5" marker-end="url(#arr)"/>
<line x1="430" y1="232" x2="430" y2="270" stroke="#2E75B6" stroke-width="1.5" marker-end="url(#arr)"/>
<line x1="570" y1="232" x2="600" y2="270" stroke="#2E75B6" stroke-width="1.5" marker-end="url(#arr)"/>
<rect x="20" y="272" width="140" height="52" rx="6" fill="#F0F7FF" stroke="#2E75B6" stroke-width="1"/>
<text x="90" y="293" text-anchor="middle" font-family="Arial" font-size="11" font-weight="bold" fill="#1F4E79">7" Touch LCD</text>
<text x="90" y="311" text-anchor="middle" font-family="Arial" font-size="10" fill="#444">In-Cell ITF</text>
<rect x="170" y="272" width="140" height="52" rx="6" fill="#F0F7FF" stroke="#2E75B6" stroke-width="1"/>
<text x="240" y="293" text-anchor="middle" font-family="Arial" font-size="11" font-weight="bold" fill="#1F4E79">{switch_type}</text>
<text x="240" y="311" text-anchor="middle" font-family="Arial" font-size="10" fill="#444">Toggle / Momentary</text>
<rect x="360" y="272" width="140" height="52" rx="6" fill="#F0F7FF" stroke="#2E75B6" stroke-width="1"/>
<text x="430" y="293" text-anchor="middle" font-family="Arial" font-size="11" font-weight="bold" fill="#1F4E79">Sound Module</text>
<text x="430" y="311" text-anchor="middle" font-family="Arial" font-size="10" fill="#444">Alarm · Touch sound</text>
<rect x="510" y="272" width="170" height="52" rx="6" fill="#F0F7FF" stroke="#2E75B6" stroke-width="1"/>
<text x="595" y="293" text-anchor="middle" font-family="Arial" font-size="11" font-weight="bold" fill="#1F4E79">LED Indicator</text>
<text x="595" y="311" text-anchor="middle" font-family="Arial" font-size="10" fill="#444">Off/Standby/Ready/Emit</text>
<line x1="350" y1="148" x2="350" y2="368" stroke="#1F4E79" stroke-width="1.8" stroke-dasharray="6,3" marker-end="url(#arr)"/>
<rect x="130" y="370" width="440" height="50" rx="8" fill="#1F4E79"/>
<text x="350" y="392" text-anchor="middle" font-family="Arial" font-size="13" font-weight="bold" fill="white">Control Software (GUI + Driver)</text>
<text x="350" y="410" text-anchor="middle" font-family="Arial" font-size="11" fill="#B5D4F4">RS-232 Serial · GUI on RPi 3B+ · Driver on STM32F207</text>
<line x1="210" y1="420" x2="150" y2="452" stroke="#0F6E56" stroke-width="1.8" marker-end="url(#arr2)"/>
<line x1="350" y1="420" x2="350" y2="452" stroke="#0F6E56" stroke-width="1.8" marker-end="url(#arr2)"/>
<line x1="490" y1="420" x2="550" y2="452" stroke="#0F6E56" stroke-width="1.8" marker-end="url(#arr2)"/>
<rect x="30" y="454" width="220" height="52" rx="6" fill="#E8F5EE" stroke="#0F6E56" stroke-width="1.2"/>
<text x="140" y="476" text-anchor="middle" font-family="Arial" font-size="11" font-weight="bold" fill="#085041">Laser Module</text>
<text x="140" y="494" text-anchor="middle" font-family="Arial" font-size="10" fill="#0F6E56">{laser_label}</text>
<rect x="265" y="454" width="170" height="52" rx="6" fill="#E8F5EE" stroke="#0F6E56" stroke-width="1.2"/>
<text x="350" y="476" text-anchor="middle" font-family="Arial" font-size="11" font-weight="bold" fill="#085041">Sensors</text>
<text x="350" y="494" text-anchor="middle" font-family="Arial" font-size="10" fill="#0F6E56">Temp · Fiber · Interlock</text>
<rect x="450" y="454" width="220" height="52" rx="6" fill="#E8F5EE" stroke="#0F6E56" stroke-width="1.2"/>
<text x="560" y="476" text-anchor="middle" font-family="Arial" font-size="11" font-weight="bold" fill="#085041">Cooling + Battery</text>
<text x="560" y="494" text-anchor="middle" font-family="Arial" font-size="10" fill="#0F6E56">TEC · Fan · Charge Monitor</text>
<text x="350" y="530" text-anchor="middle" font-family="Arial" font-size="11" font-style="italic" fill="#555">Figure 1 — General interfaces with the {name}</text>
</svg>'''
    return cairosvg.svg2png(bytestring=svg.encode(), dpi=150)


def generate_figure2(device_data: dict) -> bytes:
    """Figure 2 — GUI Software Architecture"""
    name = device_data.get("name", "Device")
    wav_a = device_data.get("specs", {}).get("wavelength_a", "")
    wav_b = device_data.get("specs", {}).get("wavelength_b", "")
    switch_type = device_data.get("specs", {}).get("switch_type", "Footswitch")
    laser_row = f"{wav_a} nm + {wav_b} nm" if wav_a else "Laser Module"

    svg = f'''<svg width="700" height="500" xmlns="http://www.w3.org/2000/svg">
<rect width="700" height="500" fill="white"/>
<defs>
  <marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
    <path d="M0 1.5L9 5L0 8.5Z" fill="#1F4E79"/>
  </marker>
</defs>
<rect x="20" y="20" width="295" height="400" rx="12" fill="#E6F1FB" stroke="#2E75B6" stroke-width="2"/>
<rect x="20" y="20" width="295" height="44" rx="12" fill="#2E75B6"/>
<rect x="20" y="52" width="295" height="12" fill="#2E75B6"/>
<text x="167" y="40" text-anchor="middle" font-family="Arial" font-size="13" font-weight="bold" fill="white">GUI Software</text>
<text x="167" y="56" text-anchor="middle" font-family="Arial" font-size="10" fill="white">Raspberry Pi 3B+ · Linux · Qt 5.12</text>
<rect x="36" y="76" width="263" height="36" rx="5" fill="white" stroke="#2E75B6" stroke-width="1"/>
<text x="167" y="99" text-anchor="middle" font-family="Arial" font-size="11" font-weight="bold" fill="#1F4E79">7" Touch LCD (In-Cell ITF)</text>
<rect x="36" y="120" width="263" height="36" rx="5" fill="white" stroke="#2E75B6" stroke-width="1"/>
<text x="167" y="143" text-anchor="middle" font-family="Arial" font-size="11" font-weight="bold" fill="#1F4E79">Sound Module</text>
<rect x="36" y="164" width="263" height="36" rx="5" fill="white" stroke="#2E75B6" stroke-width="1"/>
<text x="167" y="187" text-anchor="middle" font-family="Arial" font-size="11" font-weight="bold" fill="#1F4E79">Wi-Fi Module</text>
<rect x="36" y="208" width="263" height="36" rx="5" fill="white" stroke="#2E75B6" stroke-width="1"/>
<text x="167" y="231" text-anchor="middle" font-family="Arial" font-size="11" font-weight="bold" fill="#1F4E79">Storage (MicroSD)</text>
<rect x="36" y="252" width="263" height="36" rx="5" fill="white" stroke="#2E75B6" stroke-width="1"/>
<text x="167" y="275" text-anchor="middle" font-family="Arial" font-size="11" font-weight="bold" fill="#1F4E79">UI Pages · Protocols · Settings</text>
<rect x="36" y="296" width="263" height="36" rx="5" fill="white" stroke="#2E75B6" stroke-width="1"/>
<text x="167" y="319" text-anchor="middle" font-family="Arial" font-size="11" font-weight="bold" fill="#1F4E79">Fitzpatrick / Chronicity Logic</text>
<rect x="36" y="340" width="263" height="36" rx="5" fill="white" stroke="#2E75B6" stroke-width="1"/>
<text x="167" y="363" text-anchor="middle" font-family="Arial" font-size="11" font-weight="bold" fill="#1F4E79">Help · Anatomy Library</text>
<rect x="270" y="198" width="160" height="56" rx="10" fill="#1F4E79"/>
<text x="350" y="220" text-anchor="middle" font-family="Arial" font-size="12" font-weight="bold" fill="white">RS-232</text>
<text x="350" y="238" text-anchor="middle" font-family="Arial" font-size="10" fill="#B5D4F4">115200 baud</text>
<text x="350" y="252" text-anchor="middle" font-family="Arial" font-size="10" fill="#B5D4F4">Little-endian</text>
<line x1="315" y1="226" x2="286" y2="226" stroke="white" stroke-width="2" marker-end="url(#arr)"/>
<line x1="385" y1="226" x2="414" y2="226" stroke="white" stroke-width="2" marker-end="url(#arr)"/>
<rect x="385" y="20" width="295" height="400" rx="12" fill="#FEF3E2" stroke="#C07A00" stroke-width="2"/>
<rect x="385" y="20" width="295" height="44" rx="12" fill="#C07A00"/>
<rect x="385" y="52" width="295" height="12" fill="#C07A00"/>
<text x="532" y="40" text-anchor="middle" font-family="Arial" font-size="13" font-weight="bold" fill="white">Driver Software</text>
<text x="532" y="56" text-anchor="middle" font-family="Arial" font-size="10" fill="white">STM32F207 · Keil · C++</text>
<rect x="401" y="76" width="263" height="36" rx="5" fill="white" stroke="#C07A00" stroke-width="1"/>
<text x="532" y="99" text-anchor="middle" font-family="Arial" font-size="11" font-weight="bold" fill="#7A4A00">Laser ({laser_row})</text>
<rect x="401" y="120" width="263" height="36" rx="5" fill="white" stroke="#C07A00" stroke-width="1"/>
<text x="532" y="143" text-anchor="middle" font-family="Arial" font-size="11" font-weight="bold" fill="#7A4A00">Temperature Sensors</text>
<rect x="401" y="164" width="263" height="36" rx="5" fill="white" stroke="#C07A00" stroke-width="1"/>
<text x="532" y="187" text-anchor="middle" font-family="Arial" font-size="11" font-weight="bold" fill="#7A4A00">{switch_type} + Fiber Sensor</text>
<rect x="401" y="208" width="263" height="36" rx="5" fill="white" stroke="#C07A00" stroke-width="1"/>
<text x="532" y="231" text-anchor="middle" font-family="Arial" font-size="11" font-weight="bold" fill="#7A4A00">Interlock</text>
<rect x="401" y="252" width="263" height="36" rx="5" fill="white" stroke="#C07A00" stroke-width="1"/>
<text x="532" y="275" text-anchor="middle" font-family="Arial" font-size="11" font-weight="bold" fill="#7A4A00">Cooling System (TEC + Fan)</text>
<rect x="401" y="296" width="263" height="36" rx="5" fill="white" stroke="#C07A00" stroke-width="1"/>
<text x="532" y="319" text-anchor="middle" font-family="Arial" font-size="11" font-weight="bold" fill="#7A4A00">Battery Monitor + ADC</text>
<rect x="401" y="340" width="263" height="36" rx="5" fill="white" stroke="#C07A00" stroke-width="1"/>
<text x="532" y="363" text-anchor="middle" font-family="Arial" font-size="11" font-weight="bold" fill="#7A4A00">LED Status Indicator</text>
<rect x="20" y="430" width="660" height="30" rx="6" fill="#F0F0F0" stroke="#CCCCCC" stroke-width="1"/>
<text x="350" y="450" text-anchor="middle" font-family="Arial" font-size="10" fill="#444">Timers: 1 ms · ADC: 200 ms · Battery: 300 ms</text>
<text x="350" y="488" text-anchor="middle" font-family="Arial" font-size="11" font-style="italic" fill="#555">Figure 2 — Software of {name}</text>
</svg>'''
    return cairosvg.svg2png(bytestring=svg.encode(), dpi=150)


def generate_figure3(device_data: dict) -> bytes:
    """Figure 3 — Driver Software Architecture"""
    name = device_data.get("name", "Device")
    wav_a = device_data.get("specs", {}).get("wavelength_a", "")
    wav_b = device_data.get("specs", {}).get("wavelength_b", "")
    switch_type = device_data.get("specs", {}).get("switch_type", "Footswitch")

    svg = f'''<svg width="700" height="380" xmlns="http://www.w3.org/2000/svg">
<rect width="700" height="380" fill="white"/>
<defs>
  <marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
    <path d="M0 1.5L9 5L0 8.5Z" fill="#1F4E79"/>
  </marker>
</defs>
<rect x="250" y="20" width="200" height="44" rx="8" fill="#C07A00"/>
<text x="350" y="47" text-anchor="middle" font-family="Arial" font-size="13" font-weight="bold" fill="white">Driver Software — STM32F207</text>
<line x1="100" y1="64" x2="100" y2="94" stroke="#C07A00" stroke-width="1.5" marker-end="url(#arr)"/>
<line x1="230" y1="64" x2="230" y2="94" stroke="#C07A00" stroke-width="1.5" marker-end="url(#arr)"/>
<line x1="350" y1="64" x2="350" y2="94" stroke="#C07A00" stroke-width="1.5" marker-end="url(#arr)"/>
<line x1="470" y1="64" x2="470" y2="94" stroke="#C07A00" stroke-width="1.5" marker-end="url(#arr)"/>
<line x1="600" y1="64" x2="600" y2="94" stroke="#C07A00" stroke-width="1.5" marker-end="url(#arr)"/>
<path d="M100 64 L100 54 L600 54" fill="none" stroke="#C07A00" stroke-width="1.5"/>
<rect x="30" y="96" width="140" height="70" rx="7" fill="#FEF3E2" stroke="#C07A00" stroke-width="1.2"/>
<text x="100" y="122" text-anchor="middle" font-family="Arial" font-size="11" font-weight="bold" fill="#7A4A00">Laser Module</text>
<text x="100" y="140" text-anchor="middle" font-family="Arial" font-size="9" fill="#C07A00">{wav_a} nm</text>
<text x="100" y="156" text-anchor="middle" font-family="Arial" font-size="9" fill="#C07A00">{wav_b} nm</text>
<rect x="180" y="96" width="140" height="70" rx="7" fill="#FEF3E2" stroke="#C07A00" stroke-width="1.2"/>
<text x="250" y="118" text-anchor="middle" font-family="Arial" font-size="11" font-weight="bold" fill="#7A4A00">Temp Sensors</text>
<text x="250" y="138" text-anchor="middle" font-family="Arial" font-size="9" fill="#C07A00">Laser diode</text>
<text x="250" y="154" text-anchor="middle" font-family="Arial" font-size="9" fill="#C07A00">Battery</text>
<rect x="330" y="96" width="140" height="70" rx="7" fill="#FEF3E2" stroke="#C07A00" stroke-width="1.2"/>
<text x="400" y="118" text-anchor="middle" font-family="Arial" font-size="11" font-weight="bold" fill="#7A4A00">{switch_type}</text>
<text x="400" y="138" text-anchor="middle" font-family="Arial" font-size="9" fill="#C07A00">Fiber Sensor</text>
<text x="400" y="154" text-anchor="middle" font-family="Arial" font-size="9" fill="#C07A00">Interlock</text>
<rect x="480" y="96" width="140" height="70" rx="7" fill="#FEF3E2" stroke="#C07A00" stroke-width="1.2"/>
<text x="550" y="118" text-anchor="middle" font-family="Arial" font-size="11" font-weight="bold" fill="#7A4A00">Cooling</text>
<text x="550" y="138" text-anchor="middle" font-family="Arial" font-size="9" fill="#C07A00">TEC + Fan</text>
<text x="550" y="154" text-anchor="middle" font-family="Arial" font-size="9" fill="#C07A00">Battery ADC</text>
<rect x="20" y="200" width="660" height="44" rx="8" fill="#1F4E79"/>
<text x="350" y="220" text-anchor="middle" font-family="Arial" font-size="12" font-weight="bold" fill="white">Software Timers</text>
<text x="350" y="237" text-anchor="middle" font-family="Arial" font-size="10" fill="#B5D4F4">1 ms — timer eval · 200 ms — ADC read · 300 ms — battery process</text>
<rect x="20" y="270" width="310" height="44" rx="8" fill="#E6F1FB" stroke="#2E75B6" stroke-width="1.2"/>
<text x="175" y="297" text-anchor="middle" font-family="Arial" font-size="11" font-weight="bold" fill="#1F4E79">Panel Control Processes</text>
<rect x="370" y="270" width="310" height="44" rx="8" fill="#E6F1FB" stroke="#2E75B6" stroke-width="1.2"/>
<text x="525" y="297" text-anchor="middle" font-family="Arial" font-size="11" font-weight="bold" fill="#1F4E79">LED + Fan Control</text>
<text x="350" y="358" text-anchor="middle" font-family="Arial" font-size="11" font-style="italic" fill="#555">Figure 3 — Driver Software Architecture — {name}</text>
</svg>'''
    return cairosvg.svg2png(bytestring=svg.encode(), dpi=150)


def generate_figure4(device_data: dict) -> bytes:
    """Figure 4 — Serial Communication Interface"""
    name = device_data.get("name", "Device")
    wav_a = device_data.get("specs", {}).get("wavelength_a", "")
    wav_b = device_data.get("specs", {}).get("wavelength_b", "")

    svg = f'''<svg width="700" height="420" xmlns="http://www.w3.org/2000/svg">
<rect width="700" height="420" fill="white"/>
<defs>
  <marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
    <path d="M0 1.5L9 5L0 8.5Z" fill="#1F4E79"/>
  </marker>
  <marker id="arr2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
    <path d="M0 1.5L9 5L0 8.5Z" fill="#C07A00"/>
  </marker>
</defs>
<rect x="20" y="30" width="240" height="300" rx="12" fill="#E6F1FB" stroke="#2E75B6" stroke-width="2"/>
<rect x="20" y="30" width="240" height="40" rx="12" fill="#2E75B6"/>
<rect x="20" y="58" width="240" height="12" fill="#2E75B6"/>
<text x="140" y="55" text-anchor="middle" font-family="Arial" font-size="12" font-weight="bold" fill="white">GUI (Panel)</text>
<text x="140" y="100" text-anchor="middle" font-family="Arial" font-size="10" fill="#1F4E79">STOP / START</text>
<text x="140" y="120" text-anchor="middle" font-family="Arial" font-size="10" fill="#1F4E79">Set Power</text>
<text x="140" y="140" text-anchor="middle" font-family="Arial" font-size="10" fill="#1F4E79">Set Aiming Beam</text>
<text x="140" y="160" text-anchor="middle" font-family="Arial" font-size="10" fill="#1F4E79">Save Calibration</text>
<text x="140" y="180" text-anchor="middle" font-family="Arial" font-size="10" fill="#1F4E79">Read Status</text>
<text x="140" y="200" text-anchor="middle" font-family="Arial" font-size="10" fill="#1F4E79">Read Calibration</text>
<text x="140" y="240" text-anchor="middle" font-family="Arial" font-size="10" font-weight="bold" fill="#2E75B6">Laser A: {wav_a} nm</text>
<text x="140" y="258" text-anchor="middle" font-family="Arial" font-size="10" font-weight="bold" fill="#2E75B6">Laser B: {wav_b} nm</text>
<rect x="230" y="160" width="240" height="80" rx="10" fill="#1F4E79"/>
<text x="350" y="192" text-anchor="middle" font-family="Arial" font-size="13" font-weight="bold" fill="white">RS-232</text>
<text x="350" y="212" text-anchor="middle" font-family="Arial" font-size="10" fill="#B5D4F4">Baudrate: 115200</text>
<text x="350" y="228" text-anchor="middle" font-family="Arial" font-size="10" fill="#B5D4F4">Little-endian · XOR checksum</text>
<line x1="260" y1="200" x2="232" y2="200" stroke="white" stroke-width="2" marker-end="url(#arr)"/>
<line x1="440" y1="200" x2="468" y2="200" stroke="white" stroke-width="2" marker-end="url(#arr)"/>
<rect x="440" y="30" width="240" height="300" rx="12" fill="#FEF3E2" stroke="#C07A00" stroke-width="2"/>
<rect x="440" y="30" width="240" height="40" rx="12" fill="#C07A00"/>
<rect x="440" y="58" width="240" height="12" fill="#C07A00"/>
<text x="560" y="55" text-anchor="middle" font-family="Arial" font-size="12" font-weight="bold" fill="white">Driver (Main) — STM32F207</text>
<text x="560" y="100" text-anchor="middle" font-family="Arial" font-size="10" fill="#7A4A00">Send Status</text>
<text x="560" y="120" text-anchor="middle" font-family="Arial" font-size="10" fill="#7A4A00">Send Calibration</text>
<text x="560" y="140" text-anchor="middle" font-family="Arial" font-size="10" fill="#7A4A00">Send Power (calibration)</text>
<text x="560" y="160" text-anchor="middle" font-family="Arial" font-size="10" fill="#7A4A00">Error commands</text>
<text x="560" y="200" text-anchor="middle" font-family="Arial" font-size="10" font-weight="bold" fill="#C07A00">Temperature readings</text>
<text x="560" y="220" text-anchor="middle" font-family="Arial" font-size="10" font-weight="bold" fill="#C07A00">Battery state</text>
<text x="560" y="240" text-anchor="middle" font-family="Arial" font-size="10" font-weight="bold" fill="#C07A00">Handswitch state</text>
<rect x="20" y="352" width="660" height="30" rx="6" fill="#F0F0F0" stroke="#CCCCCC" stroke-width="1"/>
<text x="350" y="372" text-anchor="middle" font-family="Arial" font-size="10" fill="#444">ACK byte: 0xaaaa · Sequence number · XOR checksum · Little-endian · Min interval: 10 ms</text>
<text x="350" y="408" text-anchor="middle" font-family="Arial" font-size="11" font-style="italic" fill="#555">Figure 4 — Serial Communication Interface (GUI ↔ Driver) — {name}</text>
</svg>'''
    return cairosvg.svg2png(bytestring=svg.encode(), dpi=150)


def generate_figure5(device_data: dict) -> bytes:
    """Figure 5 — Software Specifications Table"""
    name = device_data.get("name", "Device")
    driver_ver = device_data.get("driver_version", "01")
    gui_ver = device_data.get("gui_version", "1.0.0")

    rows_svg = ''.join([
        '''<rect x="20" y="{y}" width="220" height="36" fill="{fill}" stroke="#CCCCCC" stroke-width="0.8"/>
<text x="130" y="{t}" text-anchor="middle" font-family="Arial" font-size="11" fill="#333">{r0}</text>
<rect x="240" y="{y}" width="220" height="36" fill="{fill}" stroke="#CCCCCC" stroke-width="0.8"/>
<text x="350" y="{t}" text-anchor="middle" font-family="Arial" font-size="11" fill="#333">{r1}</text>
<rect x="460" y="{y}" width="220" height="36" fill="{fill}" stroke="#CCCCCC" stroke-width="0.8"/>
<text x="570" y="{t}" text-anchor="middle" font-family="Arial" font-size="11" fill="#666">{r2}</text>'''.format(
            y=110 + i * 36,
            t=133 + i * 36,
            fill='#F8F9FA' if i % 2 == 0 else 'white',
            r0=row[0],
            r1=row[1],
            r2=row[2],
        )
        for i, row in enumerate([
            ("Keil", "QT Creator", "Code Environment"),
            ("C++", "C++ and QML", "Programming Languages"),
            ("-", "QT 5.12.11", "Framework"),
            ("Keil Compiler", "GCC", "Compiler"),
            ("-", "Linux", "Operating System"),
            ("STM32F207/217", "Raspberry Pi 3B+", "Hardware"),
            (driver_ver, gui_ver, "Software Version"),
        ])
    ])

    svg = f'''<svg width="700" height="340" xmlns="http://www.w3.org/2000/svg">
<rect width="700" height="340" fill="white"/>
<rect x="20" y="20" width="660" height="44" rx="8" fill="#1F4E79"/>
<text x="350" y="47" text-anchor="middle" font-family="Arial" font-size="14" font-weight="bold" fill="white">Software Specifications — {name}</text>
<rect x="20" y="74" width="220" height="36" rx="0" fill="#D5E8F0" stroke="#CCCCCC" stroke-width="0.8"/>
<text x="130" y="97" text-anchor="middle" font-family="Arial" font-size="12" font-weight="bold" fill="#1F4E79">Driver Software</text>
<rect x="240" y="74" width="220" height="36" rx="0" fill="#D5E8F0" stroke="#CCCCCC" stroke-width="0.8"/>
<text x="350" y="97" text-anchor="middle" font-family="Arial" font-size="12" font-weight="bold" fill="#1F4E79">GUI Software</text>
<rect x="460" y="74" width="220" height="36" rx="0" fill="#D5E8F0" stroke="#CCCCCC" stroke-width="0.8"/>
<text x="570" y="97" text-anchor="middle" font-family="Arial" font-size="12" font-weight="bold" fill="#1F4E79">Category</text>
{rows_svg}
<text x="350" y="320" text-anchor="middle" font-family="Arial" font-size="11" font-style="italic" fill="#555">Figure 5 — Software Specifications and Platform Stack — {name}</text>
</svg>'''
    return cairosvg.svg2png(bytestring=svg.encode(), dpi=150)


def generate_all_figures(device_data: dict, output_dir: str) -> dict:
    """Generate all figures and save to output directory."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    uid = str(uuid.uuid4())[:8]
    paths = {}

    generators = {
        "fig1": generate_figure1,
        "fig2": generate_figure2,
        "fig3": generate_figure3,
        "fig4": generate_figure4,
        "fig5": generate_figure5,
    }

    for name, gen_func in generators.items():
        png_bytes = gen_func(device_data)
        filepath = out / f"{name}_{uid}.png"
        with open(filepath, "wb") as f:
            f.write(png_bytes)
        paths[name] = str(filepath)

    return paths
