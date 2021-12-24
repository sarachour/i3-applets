import time
import pexpect
import subprocess
import sys
import numpy as np
from datetime import datetime

from OuiLookup import OuiLookup



class BluetoothctlError(Exception):
    """This exception is raised, when bluetoothctl fails to start."""
    pass


class Bluetoothctl:
    """A wrapper for bluetoothctl utility."""

    def __init__(self):
        out = subprocess.check_output("rfkill unblock bluetooth", shell = True)
        self.child = pexpect.spawn("bluetoothctl", echo = False)
        self.available_devices = {}
        self.paired_devices = {}

    def get_output(self, command, pause = 0):
        """Run a command in bluetoothctl prompt, return output as a list of lines."""
        self.child.send(command + "\n")
        time.sleep(pause)
        start_failed = self.child.expect(["bluetooth", pexpect.EOF])

        if start_failed:
            raise BluetoothctlError("Bluetoothctl failed after running " + command)

        text = self.child.before.decode("utf-8")
        return text.split("\r\n")

    def stop_scan(self):
        """Start bluetooth scanning process."""
        try:
            out = self.get_output("scan off")
        except BluetoothctlError as e:
            print(e)
            return None


    def start_scan(self):
        """Start bluetooth scanning process."""
        try:
            out = self.get_output("scan on")
        except BluetoothctlError as e:
            print(e)
            return None

    def make_discoverable(self):
        """Make device discoverable."""
        try:
            out = self.get_output("discoverable on")
        except BluetoothctlError as e:
            print(e)
            return None

    def parse_device_info(self, info_string):
        """Parse a string corresponding to a device."""
        device = {}
        block_list = ["[\x1b[0;", "removed"]
        string_valid = not any(keyword in info_string for keyword in block_list)

        if string_valid:
            try:
                device_position = info_string.index("Device")
            except ValueError:
                pass
            else:
                if device_position > -1:
                    attribute_list = info_string[device_position:].split(" ", 2)
                    device = {
                        "mac_address": attribute_list[1],
                        "name": attribute_list[2]
                    }

        return device

    def _postprocess(self,device_dict,devices):
        def is_garbage_name(name,mac):
            if name == mac or \
               name == mac.replace(":","-") or \
               "UUIDs" in name or \
               "ManufacturerData" in name or \
               "TxPower" in name or \
               "RSSI" in name:
                return True
            return False

        for dev in devices:
            mac_addr = dev['mac_address']
            if not mac_addr in device_dict:
                device_dict[mac_addr] = {'name':None,  \
                                         "TxPower": None,\
                                         "RSSI": None, \
                                         'mac': mac_addr, \
                                         'time':datetime.now()}

                lookup = list(OuiLookup().query(mac_addr)[0].values())[0]
                if not lookup is None:
                    device_dict[mac_addr]['name'] = "[OUI] %s" % lookup

            device_dict[mac_addr]['time'] = datetime.now()
            if is_garbage_name(dev['name'],mac_addr):
                continue

            if 'TxPower' in dev['name'] and ':' in dev['name']:
                device_dict[mac_addr]['TxPower'] = int(dev['name'].split(":")[1].strip())

            elif 'RSSI' in dev['name'] and ":" in dev['name']:
                device_dict[mac_addr]['RSSI'] = int(dev['name'].split(":")[1].strip())

            if not is_garbage_name(dev['name'],mac_addr):
                device_dict[mac_addr]['name'] = dev['name']

        return device_dict

    def _sort_devices(self,devices_by_key):
        mac_list = []
        value_list = []
        for mac,data in devices_by_key.items():
            mac_list.append(mac)
            value_list.append((data['name'] if not data['name'] is None else 'z' + mac))

        indices = np.argsort(value_list)
        return list(map(lambda idx: devices_by_key[mac_list[idx]], indices))



    def get_available_devices(self,sort=False):
        """Return a list of tuples of paired and discoverable devices."""
        try:
            out = self.get_output("devices")
        except BluetoothctlError as e:
            print(e)
            return None
        else:
            available_devices = []
            for line in out:
                device = self.parse_device_info(line)
                if device:
                    available_devices.append(device)

            result = self._postprocess(self.available_devices, available_devices)
            if sort:
                return self._sort_devices(result)

            return result

    def get_paired_devices(self,sort=False):
        """Return a list of tuples of paired devices."""
        try:
            out = self.get_output("paired-devices")
        except BluetoothctlError as e:
            print(e)
            return None
        else:
            paired_devices = []
            for line in out:
                device = self.parse_device_info(line)
                if device:
                    paired_devices.append(device)

            result = self._postprocess(self.paired_devices, paired_devices)
            if sort:
                return self._sort_devices(result)

            return result

    def get_discoverable_devices(self,sort=False):
        """Filter paired devices out of available."""
        available = self.get_available_devices()
        paired = self.get_paired_devices()

        by_key  = {}
        for mac in available:
            if not mac in paired:
                by_key[mac] = available[mac]

        if sort:
            return self._sort_devices(by_key)
        else:
            return by_key

    def get_device_info(self, mac_address):
        """Get device info by mac address."""
        try:
            out = self.get_output("info " + mac_address)
        except BluetoothctlError as e:
            print(e)
            return None
        else:
            return out

    def pair(self, mac_address):
        """Try to pair with a device by mac address."""
        try:
            out = self.get_output("pair " + mac_address, 4)
        except BluetoothctlError as e:
            print(e)
            return None
        else:
            res = self.child.expect(["Failed to pair", "Pairing successful", pexpect.EOF])
            success = True if res == 1 else False
            return success

    def remove(self, mac_address):
        """Remove paired device by mac address, return success of the operation."""
        try:
            out = self.get_output("remove " + mac_address, 3)
        except BluetoothctlError as e:
            print(e)
            return None
        else:
            res = self.child.expect(["not available", "Device has been removed", pexpect.EOF])
            success = True if res == 1 else False
            return success

    def connect(self, mac_address):
        """Try to connect to a device by mac address."""
        try:
            out = self.get_output("connect " + mac_address, 2)
        except BluetoothctlError as e:
            print(e)
            return None
        else:
            res = self.child.expect(["Failed to connect", "Connection successful", pexpect.EOF])
            success = True if res == 1 else False
            return success

    def disconnect(self, mac_address):
        """Try to disconnect to a device by mac address."""
        try:
            out = self.get_output("disconnect " + mac_address, 2)
        except BluetoothctlError as e:
            print(e)
            return None
        else:
            res = self.child.expect(["Failed to disconnect", "Successful disconnected", pexpect.EOF])
            success = True if res == 1 else False
            return success
