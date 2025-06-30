#!/usr/bin/env python3

# Raspberry Pi            SD card SPI Module
# ------------            ----------------
# Pin 19 (GPIO10 MOSI) ->  DI
# Pin 21 (GPIO9  MISO) ->  DO
# Pin 23 (GPIO11 SCLK) ->  CLK
# Pin 24 (GPIO8  CE0 ) ->  CS
# Pin 6  (GND)         ->  GND
# Pin 1  (3.3V)        ->  VCC

# Byte #              Description                 Number of bytes         Value
# 1                   SD Identifier               2                       Hex; 0x4453
# 3                   Manufacture date            6                       ASCII ; YYMMDD
# 9                   Health Status in % used     1                       Hex; Calculated
# 10-11               Reserved                    2                       Reserved
# 12-13               Feature Revision            2                       Hex; Refer to Generation identifier The generation identifier is used to track updates in the health status register implementation. 
# 14                  Reserved                    1                       Reserved
# 15                  Generation Identifier       1                       Hex; Refer to Generation Identifier section
# 16-49               Reserved                    34                      Reserved
# 50-81               Programmable Product String 32                      ASCII; default set as “SanDisk” followed by 0x20 (ASCII spaces)
# 82-405              Reserved                    324                     Reserved
# 406-411             Reserved                    6                       Reserved
# 412-512             Reserved                    99                      Reserved

import spidev
import time
import json
import platform
from datetime import datetime
import subprocess

spi = spidev.SpiDev()

def open_spi():
    spi.open(0, 0)  # /dev/spidev0.0
    spi.max_speed_hz = 400000
    for _ in range(10):
        spi.xfer2([0xFF])

def send_cmd(cmd, arg, crc):
    spi.xfer2([0xFF])
    packet = [
        0x40 | cmd,
        (arg >> 24) & 0xFF,
        (arg >> 16) & 0xFF,
        (arg >> 8) & 0xFF,
        arg & 0xFF,
        crc
    ]
    spi.xfer2(packet)
    for _ in range(10):
        r = spi.xfer2([0xFF])[0]
        if r & 0x80 == 0:
            return r
    return -1

def read_data_block():
    for _ in range(1000):
        token = spi.xfer2([0xFF])[0]
        if token == 0xFE:
            break
        time.sleep(0.001)
    else:
        return None
    data = spi.readbytes(512 + 2)
    return data[:-2]

def init_card():
    if send_cmd(0, 0x00000000, 0x95) != 0x01:
        return False
    if send_cmd(8, 0x000001AA, 0x87) != 0x01:
        return False
    spi.readbytes(4)
    for _ in range(100):
        send_cmd(55, 0x00000000, 0x65)
        if send_cmd(41, 0x40000000, 0x77) == 0x00:
            return True
        time.sleep(0.1)
    return False

def parse_cmd56_data(data):
    sd_identifier = data[0:2].hex().upper()
    manufacture_date = data[2:8].decode(errors='ignore')
    percent_used = data[8]
    feature_revision = data[12:14].hex().upper()
    generation_identifier = data[14]
    product_string = data[49:81].decode(errors='ignore').strip()

    return {
        "version": get_sys_version(),
        "date": datetime.utcnow().isoformat(timespec='seconds'),
        "device": "/dev/spidev0.0",
        "method": "sandisk",
        "signature": f"0x{data[0]:02X} 0x{data[1]:02X}",
        "SanDisk": sd_identifier == "4453",
        "manufactureYYMMDD": manufacture_date,
        "healthStatusPercentUsed": percent_used,
        "featureRevision": f"0x{feature_revision}",
        "generationIdentifier": generation_identifier,
        "productString": product_string,
        "success": True
    }

def get_sys_version():
    try:
        out = subprocess.check_output(["uname", "-a"]).decode()
        parts = out.strip().split()
        kernel = parts[2]
        arch = platform.machine()
        return f"v{kernel} {arch}"
    except:
        return "vUnknown"

def dump_data_block(data):
    for i in range(0, len(data), 16):
        chunk = data[i:i+16]
        hex_str = ' '.join(f'{b:02X}' for b in chunk)
        print(f"{i:03d}:  {hex_str}")

def main():
    open_spi()
    result = {
        "version": get_sys_version(),
        "date": datetime.utcnow().isoformat(timespec='seconds'),
        "device": "/dev/spidev0.0",
        "method": "sandisk",
        "signature": "0x00 0x00",
        "SanDisk": False,
        "manufactureYYMMDD": "",
        "healthStatusPercentUsed": 0,
        "featureRevision": "0x00",
        "generationIdentifier": 0,
        "productString": "",
        "success": False
    }

    if not init_card():
        print("[-] Card initialization failed")
        print(json.dumps(result, indent=2))
        return

    r = send_cmd(56, 0x00000001, 0x01)
    if r != 0x00:
        print("[-] CMD56 not accepted or unsupported")
        print(json.dumps(result, indent=2))
        return

    data = read_data_block()
    if not data:
        print("[-] No data block received")
        print(json.dumps(result, indent=2))
        return

    data = bytes(data)
    dump_data_block(data)
    parsed = parse_cmd56_data(data)
    print(json.dumps(parsed, indent=2))

if __name__ == "__main__":
    main()
