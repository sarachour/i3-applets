import models.bluetooth as bluelib

from textual import events
from textual.app import App
from textual.layouts.vertical import VerticalLayout
from textual.view import View
from textual.widgets import Header, Footer, Placeholder, ScrollView, Button, ButtonPressed
import time


class VerticalView(View, layout=VerticalLayout):

    def num_rows(self):
        return len(list(self.layout.get_widgets()))

    def get_row(self,idx):
        if not isinstance(idx,int):
            raise Exception("index <%s> is not an int" % (idx))

        widgets = list(self.layout.get_widgets())
        return widgets[idx]

    def update(self):
        self.layout.require_update()
        self.refresh(layout=True)

class BluetoothUI(App):

    class ScanState:
        SCANNING = 0
        NOT_SCANNING = 1

    class State:
        VIEW_DISCOVERABLE = 0
        VIEW_PAIRED = 1
        DELETE_PAIRED = 2
        DISCONNECT_PAIRED = 3


    async def on_load(self, event: events.Load) -> None:
        """Bind keys with the app loads (but before entering application mode)"""
        #await self.bind("b", "view.toggle('sidebar')", "Toggle sidebar")
        await self.bind("s", "", "Scan")
        await self.bind("p", "", "Paired")
        await self.bind("d", "", "Discoverable")
        await self.bind("c", "", "Connect")
        await self.bind("x", "", "Forget")
        await self.bind("q", "quit", "Quit")
        self.state = BluetoothUI.State.VIEW_DISCOVERABLE
        self.scan_state = BluetoothUI.ScanState.NOT_SCANNING

    def start_scan(self):
        self.bluetooth.start_scan()
        self.scan_state = BluetoothUI.ScanState.SCANNING
        self.bindings.get_key('s').description = "Stop Scan"

    def stop_scan(self):
        self.bluetooth.stop_scan()
        self.scan_state = BluetoothUI.ScanState.NOT_SCANNING
        self.bindings.get_key('s').description = "Scan"


    def view_available(self):
        devices = self.bluetooth.get_available_devices(sort=True)
        for idx,data in enumerate(devices):
            assert(idx < self.body.num_rows())
            text = "%d]\t %s\t%s\n" % (idx,data['mac'],data['name'])
            yield idx,text,data


    def view_paired(self):
        devices = self.bluetooth.get_paired_devices(sort=True)
        for idx,data in enumerate(devices):
            assert(idx < self.body.num_rows())
            text = "%d]\t %s\t%s\n" % (idx,data['mac'],data['name'])
            yield idx,text,data



    def view_discoverable(self):
        devices = self.bluetooth.get_discoverable_devices(sort=True)
        for idx,data in enumerate(devices):
            assert(idx < self.body.num_rows())
            text = "%d]\t %s\t%s\n" % (idx,data['mac'],data['name'])
            yield idx,text,data


    async def on_key(self, event):
        def clear_display():
            for idx in range(self.num_rows):
                    button = self.body.get_row(idx)
                    button.label = ""
                    button.model = None
            self.body.update()


        def handler(shortcut):
            if shortcut == "s":
                if self.scan_state == BluetoothUI.ScanState.SCANNING:
                    self.stop_scan()
                else:
                    self.start_scan()
                handler("d")

            elif shortcut == "d":
                self.state = BluetoothUI.State.VIEW_DISCOVERABLE
                clear_display()
                for idx,text,devinfo in self.view_discoverable():
                    button = self.body.get_row(idx)
                    button.label = text
                    button.model = devinfo

                self.body.update()

            elif shortcut == "p":
                self.state = BluetoothUI.State.VIEW_PAIRED
                clear_display()
                for idx,text,devinfo in self.view_paired():
                    button = self.body.get_row(idx)
                    button.label = text
                    button.model = devinfo

                self.body.update()

            else:
                print(event)


        handler(event.key)

    def handle_button_pressed(self, message: ButtonPressed) -> None:
        row_name = message.sender.name
        data = message.sender.model
        if data is None:
            return

        print(message.sender.model)
        if self.state == BluetoothUI.State.VIEW_DISCOVERABLE:
            print("PAIRING")
            self.bluetooth.pair(data['mac'])

        elif self.state == BluetoothUI.State.VIEW_PAIRED:
            print("CONNECTING")
            self.bluetooth.connect(data['mac'])
        else:
            raise Exception("not handled")

        """A message sent by the button widget"""
    async def on_mount(self, event: events.Mount) -> None:
        """Create and dock the widgets."""

        # A scrollview to contain the markdown file
        self.bluetooth = bluelib.Bluetoothctl()

        # Header / footer / dock
        self.header = Header()
        self.footer = Footer()
        await self.view.dock(self.header, edge="top")
        await self.view.dock(self.footer, edge="bottom")
        #await self.view.dock(Placeholder(), edge="right", size=30,  name="sidebar")
        def make_button(idx: int) -> Button:
            """Create a button with the given Figlet label."""
            style = DARK = "white on rgb(51,51,51)" 
            return Button("entry %d" % idx,  \
                          style=style,  \
                          name="entry.%d" % idx)

        self.num_rows = 30
        view = VerticalView()
        for idx in range(self.num_rows):
            button = make_button(idx)
            view.layout.add(button)

        # Dock the body in the remaining space
        #self.body = ScrollView(gutter=1)
        self.body = view
        await self.view.dock(self.body, edge="right")
        #await self.body.update(view)

        #await self.call_later(self.update_scan_info)
        #await self.call_later(get_markdown, "richreadme.md")


BluetoothUI.run(title="BluetoothCtl Client", log="textual.log")

'''
if __name__ == "__main__":

    print("Init bluetooth...")
    bl = Bluetoothctl()
    print("Ready!")
    bl.start_scan()

    n_sec = 5
    print("Scanning for %d seconds..." % n_sec)
    for i in range(0, n_sec):
        print(i)
        time.sleep(1)

    for dev in bl.get_discoverable_devices(sort=True):
        print(dev)
'''
