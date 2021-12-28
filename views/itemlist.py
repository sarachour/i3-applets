from picotui.widgets import *
from picotui.menu import *
from picotui.editorext import *
from picotui.defs import *

import time
import math

class WListBox2(ChoiceWidget):

    def __init__(self, w, h, items, margin=2):
        ChoiceWidget.__init__(self, 0)
        self.margin = margin
        self.width = w - margin
        self.height = h - margin

        self.w = w
        self.h = h

        if self.height <= 2:
            raise Exception("height of list box must be at least 3")


        self.items = []
        self.choice = 0
        self.y_offset = 0
        self.center = math.floor(h/2)
        self.rendering = False

    @property
    def n(self):
        return len(self.items)

    def set_lines(self, items):
        self.items = items
        self.move_sel(0)
        self.redraw()
        self.signal("changed")

    def handle_key(self, key):
        if key == KEY_UP:
            self.move_sel(-1)
        elif key == KEY_DOWN:
            self.move_sel(1)

    def move_sel(self, direction):
        self.redraw()
        new_idx = min(max(0,self.choice+ direction),self.n-1)
        self.choice = new_idx
        self.redraw()
        self.signal("changed")

    def handle_edit_key(self, key):
        pass

    def set_cursor(self):
        Widget.set_cursor(self)

    def cursor(self, state):
        # Force off
        super().cursor(False)

    def get_window(self):
        if self.choice < self.height:
            return 0

        elif self.choice >= self.n - self.height:
            return max(0, self.n - self.height )
        else:
            lo = max(self.choice - self.center,0)
            return lo


    def wr_line(self,idx):
        text = self.items[idx]
        low = self.get_window()
        if idx < low or idx > low + self.height-1:
            return

        offset = (idx-low)
        self.goto(self.x + self.margin,  \
                  self.y + offset + self.margin)
        if idx == self.choice:
            self.attr_color(C_B_BLUE,None)
        else:
            self.attr_color(C_B_WHITE,None)

        #self.wr_fixedw(text,self.width)
        self.wr_fixedw(text.strip(),self.width)
        self.attr_reset()


    def redraw(self):
        self.rendering = True
        for idx,text in enumerate(self.items):
            self.wr_line(idx)
        self.rendering = False
 
