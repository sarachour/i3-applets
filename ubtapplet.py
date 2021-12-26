from picotui.screen import Screen
from picotui.widgets import *
from picotui.menu import *
from picotui.defs import *

import models.bluetooth as bluelib
from threading import Thread, Timer
import time

def write_log(msg):
    with open("log.txt","a") as fh:
        fh.write("%s\n" % msg)

class RepeatingTimer(Timer):
    def run(self):
        while not self.finished.is_set():
            self.function(*self.args, **self.kwargs)
            self.finished.wait(self.interval)


'''
Flowchart -- write handler for parsing info from mac address.
this should tell us if it's 
'''
class BluetoothApplet:

    class ControllerState:
        ON = 0
        OFF = 1

    class ScanState:
        SCANNING = 0
        NOT_SCANNING = 1
        SCAN_PAUSED = 2

    class ViewState:
        VIEW_ALL = "all"
        VIEW_PAIRED = "paired"


    class ActionState:
        PAIRING = 0
        CONNECTING = 1
        UNPAIRING= 2
        DISCONNECTING = 3
        IDLE = 4



    def __init__(self):
        self.bluetooth = None
        self.screen = Screen()
        self.scan_state = BluetoothApplet.ScanState.NOT_SCANNING
        self.controller_state = BluetoothApplet.ControllerState.ON
        self.action_state = BluetoothApplet.ActionState.IDLE
        self.target = None

        self.bluetooth = bluelib.Bluetoothctl(rfkill_unblock=False,debug=False)

        self.view_index = 0
        self.view_order = [
            BluetoothApplet.ViewState.VIEW_PAIRED,
            BluetoothApplet.ViewState.VIEW_ALL
        ]

        def update_in_background():
            self.update_pane()
            self.update_status()

        self.update_thread = RepeatingTimer(2.0, update_in_background)



    @property
    def view_state(self):
        n = len(self.view_order)
        index = abs(self.view_index) % n
        return self.view_order[index]

    def screen_redraw(self,allow_cursor=False):
        self.update_pane()
        self.update_status()
        self.screen.attr_color(C_WHITE, C_BLUE)
        self.screen.cls()
        self.screen.attr_reset()
        self.dialog.redraw()

    def get_devices(self):
        update_scanned = self.scan_state == BluetoothApplet.ScanState.SCANNING
        update_paired = self.action_state != BluetoothApplet.ActionState.IDLE
        if update_scanned:
            self.bluetooth.flush_log()

        self.bluetooth.update_devices(update_scanned=update_scanned, \
                                      update_paired=update_paired)
        return self.bluetooth.get_devices(sort=True)

    def update_pane(self):
        self.devices = self.get_devices()

        entries = []
        for idx,data in enumerate(self.devices):
            if self.view_state == BluetoothApplet.ViewState.VIEW_PAIRED and \
               not data["paired"]:
                continue

            if data["connected"]:
                flag = "[conn]"
            elif data["paired"]:
                flag = "[pair]"
            elif not data["online"]:
                flag = " [-]  "
            else:
                flag = " [*]  "


            text = "%d]%s %s %s\n" % (idx, \
                                      flag, \
                                      data['mac_addr'], \
                                      data['name'])

            entries.append(text)

        self.frame.set_items(entries)
        self.dialog.redraw()
        #self.frame.redraw()

    def initialize(self):
        self.screen.init_tty()
        self.screen.enable_mouse()
        self.setup_ui()

        self.bluetooth.power_on()
        self.bluetooth.stop_scan()
        time.sleep(0.1)
        self.bluetooth.update_devices()
        self.bluetooth.update_devices()
        self.update_pane()

    def setup_ui(self):
        frame_height = 24
        frame_width = 96
        msg_height = 1
        ypadding = 3
        xpadding = 4
        self.dialog = Dialog(x=2,y=2,w=frame_width+xpadding*2, \
                             h=frame_height+msg_height*3 + ypadding*4,  \
                             title="bluetooth")

        yoffset = ypadding
        self.view_msg = WLabel(w=frame_width, text="<current view>")
        self.dialog.add(x=2, y=yoffset, widget=self.view_msg)
        yoffset += msg_height
        yoffset += ypadding

        self.frame = WListBox(w=frame_width, h=frame_height, items=["a","b"])
        self.dialog.add(x=2,y=yoffset, widget=self.frame)
        yoffset += frame_height

        self.status_msg = WLabel(w=frame_width, text="<status line>")
        self.debug_msg = WLabel(w=frame_width, text="<feedback>")
        self.help_msg = WLabel(w=frame_width, text="u:update | s:scan on/off | c: conn/disconn | x: del")

        yoffset += ypadding
        self.dialog.add(x=2, y=yoffset, widget=self.status_msg)
        yoffset += msg_height
        self.dialog.add(x=2, y=yoffset, widget=self.debug_msg)
        yoffset += msg_height
        self.dialog.add(x=2, y=yoffset, widget=self.help_msg)

        self.screen_redraw()
        Screen.set_screen_redraw(self.screen_redraw)

        self.update_thread.start()

    def get_selected_device(self):
        line_index = self.frame.cur_line
        return self.devices[line_index]

    def unpause_scan(self):
        if self.scan_state == BluetoothApplet.ScanState.SCAN_PAUSED:
            self.scan_state = BluetoothApplet.ScanState.SCANNING
            self.bluetooth.start_scan()


    def pause_scan(self):
        if self.scan_state == BluetoothApplet.ScanState.SCANNING:
            self.scan_state = BluetoothApplet.ScanState.SCAN_PAUSED
            self.bluetooth.stop_scan()


    def update_status(self):
        if self.view_state == BluetoothApplet.ViewState.VIEW_ALL:
            msg = "[[all devices]]"
        elif self.view_state == BluetoothApplet.ViewState.VIEW_PAIRED:
            msg = "[[paired devices]]"

        self.view_msg.t = msg
        self.view_msg.redraw()

        flags = []
        if self.controller_state == BluetoothApplet.ControllerState.ON:
            flags.append("powered on")
        else:
            flags.append("powered off")

        if self.action_state != BluetoothApplet.ActionState.IDLE:
            is_connected = self.bluetooth.is_connected(self.target)
            is_paired = self.bluetooth.is_paired(self.target)

            if self.action_state == BluetoothApplet.ActionState.CONNECTING and \
            is_connected:
                    self.action_state = BluetoothApplet.ActionState.IDLE
                    self.unpause_scan()

            if self.action_state == BluetoothApplet.ActionState.DISCONNECTING and \
            not is_connected:
                    self.action_state = BluetoothApplet.ActionState.IDLE
                    self.unpause_scan()

            if self.action_state == BluetoothApplet.ActionState.PAIRING and \
            is_paired:
                    self.action_state = BluetoothApplet.ActionState.IDLE
                    self.unpause_scan()

            if self.action_state == BluetoothApplet.ActionState.UNPAIRING and \
            not is_paired:
                    self.action_state = BluetoothApplet.ActionState.IDLE
                    self.unpause_scan()


        if self.scan_state == BluetoothApplet.ScanState.SCANNING:
            flags.append("scanning")
        elif self.scan_state == BluetoothApplet.ScanState.SCAN_PAUSED:
            flags.append("paused scan")
        else:
            pass


        if self.action_state == BluetoothApplet.ActionState.CONNECTING:
            flags.append("connecting to %s" % self.target)
        elif self.action_state == BluetoothApplet.ActionState.CONNECTING:
            flags.append("disconnecting from %s" % self.target)
        elif self.action_state == BluetoothApplet.ActionState.PAIRING:
            flags.append("pairing with %s" % self.target)
        elif self.action_state == BluetoothApplet.ActionState.UNPAIRING:
            flags.append("unpairing with %s" % self.target)


        msg = " | ".join(flags)
        self.status_msg.t = msg
        self.status_msg.redraw()


    def update_msg(self,msg):
        self.debug_msg.t = msg
        self.debug_msg.redraw()
        write_log(self.debug_msg.t)

    def run(self):
        while 1:
            key = self.dialog.get_input()
            write_log(key)

            keystr = None
            try:
                keystr = key.decode("ascii")
            except:
                keystr = None
 
            if keystr != None:
                write_log(keystr)
                if keystr == "s":
                    if self.scan_state == BluetoothApplet.ScanState.NOT_SCANNING:
                        self.bluetooth.start_scan()
                        self.scan_state = BluetoothApplet.ScanState.SCANNING
                        self.update_msg("scanning")
                    else:
                        self.pause_scan()
                        self.scan_state = BluetoothApplet.ScanState.NOT_SCANNING
                        self.update_msg("stopped")

                    self.update_status()

                elif keystr == "x":
                    dev = self.get_selected_device()
                    target_mac = dev["mac_addr"]

                    is_paired = self.bluetooth.is_paired(target_mac)
                    if is_paired:
                        self.update_msg("unpairing with %s" % (target_mac))
                        self.target = target_mac
                        self.action_state = BluetoothApplet.ActionState.UNPAIRING
                        self.pause_scan()
                        self.bluetooth.unpair(self.target)
                        self.update_status()


                elif keystr == "d":
                    dev = self.get_selected_device()
                    target_mac = dev["mac_addr"]
                    if self.action_state != BluetoothApplet.ActionState.IDLE:
                        self.update_msg("failed. There is an action already in progress.")
                        continue

                    is_connected = self.bluetooth.is_connected(target_mac)
                    if is_connected:
                        self.update_msg("disconnecting from %s" % (target_mac))
                        self.target = target_mac
                        self.action_state = BluetoothApplet.ActionState.DISCONNECTING
                        self.pause_scan()
                        self.bluetooth.disconnect(self.target)
                        self.update_status()

                    else:
                        self.update_msg("error: %s not connected" % dev["mac_addr"])



                elif keystr == "c":
                    dev = self.get_selected_device()
                    target_mac = dev["mac_addr"]

                    if self.action_state != BluetoothApplet.ActionState.IDLE:
                        self.update_msg("failed. There is an action already in progress.")
                        continue

                    is_connected = self.bluetooth.is_connected(target_mac)
                    is_paired = self.bluetooth.is_paired(target_mac)
                    if is_paired:
                        if is_connected:
                            self.update_msg("already connected to %s" % target_mac)
                            continue

                        self.update_msg("connecting to %s" % (target_mac))
                        self.target = target_mac
                        self.action_state = BluetoothApplet.ActionState.CONNECTING
                        self.pause_scan()
                        result = self.bluetooth.connect(self.target)
                        self.update_status()

                    else:
                        self.update_msg("pairing with %s" % (target_mac))
                        self.action_state = BluetoothApplet.ActionState.PAIRING
                        self.target = target_mac
                        self.pause_scan()
                        result = self.bluetooth.pair(self.target)
                        self.update_status()



                elif keystr == "t":
                    self.update_msg("turn off/on")
                    self.bluetooth.power_off()

                elif keystr == "q":
                    if self.scan_state == BluetoothApplet.ScanState.SCANNING:
                        self.bluetooth.stop_scan();
                    self.teardown()
                    return
            else:
                if key == KEY_LEFT:
                    self.view_index -= 1
                    self.update_msg("view %s #devs=%d" % (self.view_state, \
                                                       len(self.get_devices())))
                    self.update_status()


                elif key == KEY_RIGHT:
                    self.view_index += 1
                    self.update_msg("view %s #devs=%d" % (self.view_state, \
                                                       len(self.get_devices())))
                    self.update_status()

                else:
                    res = self.dialog.handle_input(key)
                    if res is not None and res is not True:
                        return

        self.teardown()

    def teardown(self):
        self.update_thread.cancel()
        self.screen.cls()
        self.screen.cursor(True)
        self.screen.disable_mouse()
        self.screen.deinit_tty()

def run_ui():
    applet = BluetoothApplet()
    try:
        applet.initialize()
        applet.run()
    finally:
        applet.teardown()


def test_info(target_mac):
    print("starting...")
    bluetooth = bluelib.Bluetoothctl(rfkill_unblock=False)
    print("powering on...")
    bluetooth.power_on()
    print("update device list")
    bluetooth.update_devices()
    for dev in bluetooth.get_devices():
        print(dev)


def test_scan():
    print("starting...")
    bluetooth = bluelib.Bluetoothctl(rfkill_unblock=False)
    print("powering on...")
    bluetooth.power_on()

    print("update device list")
    bluetooth.update_devices()
    print("scan")
    bluetooth.start_scan()
    bluetooth.stop_scan()
    print("update after scan")
    bluetooth.update_devices()
    for dev in bluetooth.get_devices():
        print(dev)

def test_connect(target_mac):
    print("starting...")
    bluetooth = bluelib.Bluetoothctl(rfkill_unblock=False,debug=True)
    print("powering on...")
    bluetooth.power_on()
    bluetooth.update_devices()
    print(bluetooth.devices)
    print("checking connectivity...")
    if bluetooth.is_connected(target_mac):
        print("disconnecting...")
        bluetooth.disconnect(target_mac,sync=False)

    print("connect...")
    is_connected = bluetooth.connect(target_mac,sync=False)
    while 1:
        data = bluetooth.get_device_info(target_mac)
        if "Connected" in data and data["Connected"]:
            print("connected!!")
            break



#test_connect("FC:E8:06:8F:30:BB")
#test_info("FC:E8:06:8F:30:BB")
#test_scan()
run_ui()
