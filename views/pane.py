from picotui.basewidget import *

class Pane(Widget):

    finish_on_esc = True

    def __init__(self, x, y, w=0, h=0, title=""):
        super().__init__()
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.children  = []

    def add(self, x, y, widget):
        isinstance(widget, Widget)
        widget.set_xy(self.x + x, self.y + y)
        self.children.append(widget)
        widget.owner = self

    def handle_mouse(self,arg0,arg1):
        return

    def handle_key(self,key):
        for w in self.children:
            if hasattr(w,"handle_key"):
                w.handle_key(key)

        return

    def autosize(self):
        w = 0
        h = 0
        for wid in self.childrens:
            w = max(w, wid.x - self.x + wid.w)
            h = max(h, wid.y - self.y + wid.h)
        self.w = self.w
        self.h = self.h

    def redraw(self):
        # Redraw widgets with cursor off
        #self.cursor(False)
        self.clear_box(self.x-1, self.y, self.w, self.h)
        self.draw_box(self.x, self.y, self.w, self.h)
        for w in self.children:
            w.redraw()
        # Then give widget in focus a chance to enable cursor
