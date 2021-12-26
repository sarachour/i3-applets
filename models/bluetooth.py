import time
import pexpect
import subprocess
import sys
import numpy as np
from datetime import datetime,timedelta
import re
import logging

from OuiLookup import OuiLookup


class BluetoothctlError(Exception):
    """This exception is raised, when bluetoothctl fails to start."""
    pass


class RecordsListHandler(logging.Handler):
    """
    A handler class which stores LogRecord entries in a list
    """
    def __init__(self):
        """
        Initiate the handler
        :param records_list: a list to store the LogRecords entries
        """
        self.records_list = []
        super().__init__()

    @property
    def entries(self):
        return self.records_list

    def emit(self, record):
        self.records_list.append(record)


# A list to store the "raw" LogRecord instances
logs_list = []

# Your logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Add the regular stream handler to print logs to the console, if you like
logger.addHandler(logging.StreamHandler(sys.stdout))

# Add the RecordsListHandler to store the log records objects


class Bluetoothctl:
    """A wrapper for bluetoothctl utility."""

    def __init__(self, rfkill_unblock=True,debug=False):
        if rfkill_unblock:
            out = subprocess.check_output("rfkill unblock bluetooth", shell = True)

        self.child = pexpect.spawn("bluetoothctl", \
                                   encoding="utf-8", \
                                   echo=True)
        self.devices = {}
        self.logfile = self.get_discover_log()
        self.child.logfile = self.logger
        self.text_buffer = []

        self.wait_for_prompt(None,0.1)

    def get_discover_log(self):
        discover_log = "/tmp/discover.log"

        def _write(*args, **kwargs):
            text = args[0]
            # Ignore other params, pexpect only use one arg
            for line in re.split(r'[\n\r]+', text):
                if line.strip() == "":
                    continue

                logger.info(line) # call the logger info method with the reworked content

            return True

        # our flush method
        def _flushFile():
            hdlr.stream.flush()

        logger = logging.getLogger('bt-discover')
        hdlr = logging.FileHandler(discover_log, \
                                   mode="w", \
                                   encoding="utf-8")
        formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
        hdlr.setFormatter(formatter)
        logger.addHandler(hdlr)
        logger.setLevel(logging.INFO)

        # give the logger the methods required by pexpect
        logger.write = _write
        logger.flush = _flushFile

        self.log_handler = RecordsListHandler()
        logger.addHandler(self.log_handler)
        self.logger = logger

    def parse_text(self,text):
        if(isinstance(text,bytes)):
            text = text.decode("utf-8")

        ansi_escape =r'(\x1B[@-_][0-?]*[ -/]*[@-~])+'
        newline = '\r\n'
        ansi_regex = re.compile(ansi_escape)
        san_text = ansi_regex.sub("", text)
        return san_text.split(newline)

    def get_output(self):
        self.text_buffer += self.parse_text(self.child.before)
        return self.text_buffer

    def clear_output(self):
        self.text_buffer = []

    def wait_for_prompt(self, command, pause = 0.1):
        """Run a command in bluetoothctl prompt, return output as a list of lines."""
        if not command is None:
            self.child.send(command + "\n")

        ansi_escape =r'(\x1b[@-_][0-?]*[ -/]*[@-~])*'
        newline = r'\r\n?'
        command_regex = newline + ansi_escape+"\[[A-Z\-a-z0-9 ]+\]" + ansi_escape + "#"
        #command_regex = ansi_escape+"\[[A-Za-z0-9 ]+\]" + ansi_escape + "#"
        command_patterns = [command_regex, \
                            pexpect.EOF]
        start_failed = self.child.expect(command_patterns, timeout=pause)

        if start_failed:
            raise BluetoothctlError("Bluetoothctl failed after running " + command)

        return self.parse_text(self.child.before)

    def _lookup_device_name(self,mac,dev_name):
        # TODO: (random), (public)
        if dev_name is None or \
           mac == dev_name or \
           dev_name == mac.replace(":","-"):
            lookup = list(OuiLookup().query(mac)[0].values())[0]
            if not lookup is None:
                return "%s (oui)" % lookup, True
            return None, True

        else:
            return dev_name, False

    def _declare_device(self,mac,name,inferred_name=False):
        if not mac in self.devices:
            self.devices[mac] = dict({"online": False, \
                                 "paired": False, \
                                 "connected": False, \
                                 "update_state": False, \
                                 "name": name, \
                                 "mac_addr": mac, \
                                 "time": datetime.now(), \
                                 "tx_power": -1, \
                                 "rssi": -1})
        elif not name is None and \
             (not inferred_name or self.devices[mac]["name"] is None):
            self.devices[mac]["name"] = name

    def _update_from_discover_log(self):
        def find_cmd_index(args):
            cmds = ["CHG", "NEW", "DEL"]
            for idx,arg in enumerate(args):
                for cmd in cmds:
                    if cmd in arg:
                        return cmd,idx
            return None,-1

        for entry in self.log_handler.entries:
            msg = entry.getMessage()
            lines = self.parse_text(msg)
            for line in lines:
                timestamp = datetime.strptime(entry.asctime.split(",")[0], \
                                            "%Y-%m-%d %H:%M:%S")
                args = line.split(" ")
                cmd,index = find_cmd_index(args)
                if len(args) < index + 2 or \
                   args[index+1] != "Device":
                    continue

                if cmd == "CHG":
                    if len(args) <= index+4:
                        continue

                    mac_addr,subcmd = args[index+2],args[index+3]
                    final_name,inferred = self._lookup_device_name(mac_addr,None)
                    self._declare_device(mac_addr,final_name,inferred_name=inferred)
                    if "RSSI" in subcmd:
                        try:
                            self.devices[mac_addr]["rssi"] = int(args[index+4])
                        except ValueError:
                            pass

                    elif "TxPower" in subcmd:
                        try:
                            self.devices[mac_addr]["tx_power"] = int(args[index+4])
                        except ValueError:
                            pass


                    elif "Name:" in subcmd or "Alias:" in subcmd:
                        self.devices[mac_addr]["name"] = " ".join(args[index+4:])

                    self.devices[mac_addr]['online'] = True
                    self.devices[mac_addr]["time"] = timestamp

                elif cmd == "NEW" and len(args) >= index+3:
                    mac_addr = args[index+2]
                    if len(args) >= index+4:
                        name = " ".join(args[index+3:])
                    else:
                        name = None

                    final_name,inferred = self._lookup_device_name(mac_addr,name)
                    self._declare_device(mac_addr, final_name, \
                                         inferred_name=inferred)
                    self.devices[mac_addr]['online'] = True
                    self.devices[mac_addr]["time"] = timestamp

                elif cmd == "DEL":
                    pass



    def _update_from_parsed_result(self,text):
        macs = []
        for line in text:
            args = line.strip().split(" ")
            if args[0] == "Device":
                mac_addr = args[1]
                name = " ".join(args[2:])
                if name == "(random)" or \
                   name == "(public)":
                    name = None

                final_name, inferred = self._lookup_device_name(mac_addr,name)
                self._declare_device(mac_addr,  \
                                     final_name, inferred_name=inferred)
                macs.append(mac_addr)
        return macs

    def _update_available_devices(self):
        try:
            self.clear_output()
            self.wait_for_prompt("devices", 0.1)
            out = self.get_output()
            self._update_from_parsed_result(out)

        except BluetoothctlError as e:
            print(e)
            return None


    def _update_paired_devices(self):
        """Return a list of tuples of paired devices."""
        try:
            self.clear_output()
            self.wait_for_prompt("paired-devices", 0.1)
            out = self.get_output()
            macs = self._update_from_parsed_result(out)
            for mac in macs:
                if self.devices[mac]["paired"] == False:
                    self.devices[mac]["update_state"] = True


        except BluetoothctlError as e:
            print(e)
            return None


    def _sort_devices(self,devices_by_key):
        mac_list = []
        value_list = []
        device_list = dict(devices_by_key)
        for mac,data in device_list.items():
            mac_list.append(mac)
            prefix = ""
            if data["connected"]:
                prefix = "AA"
            elif data["paired"]:
                prefix = "A"
            elif not data["online"]:
                prefix = "z"

            value_list.append((prefix + data['name'] if not data['name'] is None else prefix + 'z' + mac))

        indices = np.argsort(value_list)
        return list(map(lambda idx: dict(device_list[mac_list[idx]]), indices))




    def _prune_devices(self,devices, timeout):
        curr_time = datetime.now()
        expiration_time = curr_time  - timedelta(seconds=timeout)
        pruned = []
        for dev in devices:
            if dev['time'] >= expiration_time:
                pruned.append(dev)


        return pruned



    def update_devices(self,update_scanned=True,update_paired=True):
        """Filter paired devices out of available."""
        if update_scanned:
            self._update_from_discover_log()

        if update_paired:
            self._update_paired_devices()

        for dev in self.devices.values():
            if dev["update_state"]:
                self.update_device_status(dev["mac_addr"])
                dev["update_state"] = False

    def get_devices(self,sort=False):
        return self._prune_devices(self._sort_devices(self.devices), 60*3)


    def _process_device_info(self,text,mac_addr):
        indent = "\t"

        start_idx = -1
        info = {}
        for idx,line in enumerate(text):
            if "Device" in line:
                args = line.split(" ")
                this_mac_addr = args[1]
                if this_mac_addr == mac_addr and \
                   len(text) >= idx+2 and \
                   text[idx+1].startswith(indent):
                    start_idx = idx+1

        if start_idx < 0:
            self.logger.info("NO START INDEX")
            return None

        for line in text[start_idx:]:
            if not line.startswith(indent):
                self.logger.info("NOT INDENTED")
                return info

            if not ":" in line:
                self.logger.info("NO ENTRY")
                continue

            args = line.split(":")
            key,value = args[0].strip(), \
                ":".join(args[1:]).strip()

            if key == "UUID":
                key = value.split(":")[0]
                value = ":".join(value.split(":")[1:])

            if value in ["yes","no"]:
                value = True if value == "yes" else False

            info[key] = value

        self.logger.info(info)
        return info


    def get_device_info(self, mac_address):
        """Get device info by mac address."""
        try:
            self.clear_output()
            self.wait_for_prompt("info " + mac_address,0.1)
            out = self.get_output()

        except BluetoothctlError as e:
            print(e)
            return None
        else:
            res = self.child.expect(["UUID:", "not available", pexpect.EOF])
            out = self.get_output()
            infodict = self._process_device_info(out,mac_address)
            return infodict

    def is_connected(self,mac_address):
        self.update_device_status(mac_address)
        return self.devices[mac_address]["connected"]

    def is_paired(self,mac_address):
        self.update_device_status(mac_address)
        return self.devices[mac_address]["paired"]

    def update_device_status(self,mac_address):
        data = self.get_device_info(mac_address)
        if data is None:
            return False

        is_paired = "Paired" in data and data["Paired"]
        self.devices[mac_address]["paired"] = is_paired
        is_connected = "Connected" in data and data["Connected"]
        self.devices[mac_address]["connected"] = is_connected
        return is_paired


    def pair(self, mac_address):
        """Try to pair with a device by mac address."""
        try:
            self.clear_output()
            self.wait_for_prompt("pair " + mac_address, 4)
            self.get_output()
        except BluetoothctlError as e:
            print(e)
            return None
        else:
            res = self.child.expect(["Failed to pair", "Pairing successful", pexpect.EOF])
            out = self.get_output()
            success = True if res == 1 else False
            return success

    def unpair(self, mac_address):
        """Try to pair with a device by mac address."""
        try:
            self.clear_output()
            out = self.wait_for_prompt("remove " + mac_address, 4)
            self.get_output()
        except BluetoothctlError as e:
            print(e)
            return None
        else:
            res = self.child.expect(["Failed to remove", "Device has been removed", pexpect.EOF])
            out = self.get_output()
            success = True if res == 1 else False
            return success


    def remove(self, mac_address):
        """Remove paired device by mac address, return success of the operation."""
        try:
            self.clear_output()
            out = self.wait_for_prompt("remove " + mac_address, 3)
            self.get_output()
        except BluetoothctlError as e:
            print(e)
            return None
        else:
            res = self.child.expect(["not available", "Device has been removed", pexpect.EOF])
            success = True if res == 1 else False
            return success

    def connect(self, mac_address,sync=True):

        if self.is_connected(mac_address):
            return True

        try:
            self.clear_output()
            out = self.wait_for_prompt("connect " + mac_address, 2)
        except BluetoothctlError as e:
            print(e)
            return None

        else:
            if sync:
                res = self.child.expect(["Failed to connect", "Connection successful", pexpect.EOF])
                msg = self.get_output()
                success = True if res == 1 else False
                return success
            else:
                return None

    def disconnect(self, mac_address,sync=False):

        if not self.is_connected(mac_address):
            return True

        """Try to disconnect to a device by mac address."""
        try:
            self.clear_output()
            out = self.wait_for_prompt("disconnect " + mac_address, 2)
            self.get_output()
        except BluetoothctlError as e:
            print(e)
            return None
        else:
            if sync:
                res = self.child.expect(["Failed to disconnect", "Successful disconnected", pexpect.EOF])
                self.get_output()
                success = True if res == 1 else False
                return success
            else:
                return None



    def stop_scan(self):
        """Start bluetooth scanning process."""
        try:
            # turn off scanner
            self.clear_output()
            out = self.wait_for_prompt("scan off")
            self.get_output()
        except BluetoothctlError as e:
            print(e)
            return None
        else:
            res = self.child.expect(["Discovering: no", "Failed to stop discovery", pexpect.EOF])
            self.get_output()
            return res

    def flush_log(self):
            self.wait_for_prompt("list")

    def start_scan(self):
        """Start bluetooth scanning process."""
        try:
            self.clear_output()
            out = self.wait_for_prompt("scan on")
            self.get_output()
        except BluetoothctlError as e:
            print(e)
            return None
        else:
            res = self.child.expect(["Discovering: yes", "Failed to start discovery", pexpect.EOF])
            self.get_output()
            return res


    def power_off(self):
        """Make device discoverable."""
        try:
            self.clear_output()
            out = self.wait_for_prompt("power off",1)
        except BluetoothctlError as e:
            print(e)
            return None

        res = self.child.expect(["power off succeeded", pexpect.EOF])
        self.get_output()
        return res

    def power_on(self):
        """Make device discoverable."""
        try:
            self.clear_output()
            self.wait_for_prompt("power on",1)
        except BluetoothctlError as e:
            print(e)
            return None

        res = self.child.expect(["power on succeeded", pexpect.EOF])
        out = self.get_output()


    def make_discoverable(self):
        """Make device discoverable."""
        try:
            self.clear_output()
            out = self.wait_for_prompt("discoverable on")
            self.get_output()
        except BluetoothctlError as e:
            print(e)
            return None
