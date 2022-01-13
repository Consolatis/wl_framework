#!/usr/bin/env python3

import gi
import datetime

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version('GtkLayerShell', '0.1')
from gi.repository import Gtk, Gdk, GtkLayerShell, GObject

from wl_framework.loop_integrations import GLibIntegration
from wl_framework.network.connection import WaylandConnection
from wl_framework.protocols.foreign_toplevel import ForeignTopLevel

# Signal hub + Wayland connection
class Context(GObject.Object, WaylandConnection):
	def __init__(self):
		GObject.Object.__init__(self)
		WaylandConnection.__init__(self, eventloop_integration=GLibIntegration())
		self.add_signal('periodic_update', tuple())
		self.add_signal('wayland_sync')
		self.add_timer(2, self.on_periodic_update)
		self.manager = TaskManager(self)

	def add_signal(self, signal_name, signal_args=None):
		if signal_args is None:
			signal_args = (GObject.TYPE_PYOBJECT,)
		GObject.signal_new(
			signal_name, self,
			GObject.SignalFlags.RUN_LAST,
			GObject.TYPE_PYOBJECT, signal_args
		)

	def on_initial_sync(self, data):
		super().on_initial_sync(data)
		self.seat = self.display.seat
		self.emit('wayland_sync', self)

	def on_periodic_update(self):
		self.emit('periodic_update')

# Foreign Toplevel / GObject signal emitter bridge
class ToplevelManager(ForeignTopLevel):
	def __init__(self, wl_connection, context):
		super().__init__(wl_connection)
		self.context = context

	def on_toplevel_created(self, toplevel):
		self.context.emit('toplevel_new', toplevel)

	def on_toplevel_synced(self, toplevel):
		self.context.emit('toplevel_synced', toplevel)

	def on_toplevel_closed(self, toplevel):
		self.context.emit('toplevel_closed', toplevel)

# Foreign Toplevel API
# Supports direct calls or being used as event handler for a GTK widget:
# - manager.app_toggle(toplevel)
# - some_button.connect('clicked', manager.app_toggle, toplevel)
class TaskManager:
	def __init__(self, context):
		context.add_signal('toplevel_new')
		context.add_signal('toplevel_synced')
		context.add_signal('toplevel_closed')
		context.connect('wayland_sync', self.on_wl_sync)
		self.context = context
		self.manager = None

	def on_wl_sync(self, context, wl_connection):
		self.manager = ToplevelManager(wl_connection, context)

	def app_toggle(self, *args):
		toplevel = args[-1]
		if 'activated' in toplevel.states:
			toplevel.set_minimize(True)
		else:
			self.app_activate(toplevel)

	def app_activate(self, *args):
		toplevel = args[-1]
		toplevel.activate(self.context.seat)

	def app_minimize(self, *args):
		toplevel = args[-1]
		if 'minimized' in toplevel.states:
			return
		toplevel.set_minimize(True)

	def app_toggle_minimize(self, *args):
		toplevel = args[-1]
		toplevel.set_minimize('minimized' not in toplevel.states)

	def app_toggle_maximize(self, *args):
		toplevel = args[-1]
		toplevel.set_maximize('maximized' not in toplevel.states)

	def app_toggle_fullscreen(self, *args):
		toplevel = args[-1]
		toplevel.set_fullscreen('fullscreen' not in toplevel.states)

	def app_close(self, *args):
		toplevel = args[-1]
		toplevel.close()

# The actual panel
class PanelWindow(Gtk.Window):
	def __init__(self, context):
		super().__init__()
		self.context = context
		self.manager = context.manager
		self.active_button = None
		context.connect('toplevel_new', self.on_toplevel_new)
		context.connect('toplevel_synced', self.on_toplevel_synced)
		context.connect('toplevel_closed', self.on_toplevel_closed)
		context.connect('periodic_update', self.on_periodic_update)
		self._create_menu()
		box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
		box.pack_start(self._create_scroll(), True, True, 0)
		box.pack_start(self._create_clock(), False, False, 10)
		self.add(box)
		self.set_name('panel')
		self._add_style()

	def on_toplevel_new(self, context, toplevel):
		button = Gtk.Button(label='unknown')
		button.connect('clicked', self.manager.app_toggle, toplevel)
		button.connect('button-press-event', self.handle_context_menu, toplevel)
		button.show()
		toplevel.button = button
		self.box.pack_start(button, False, False, 0)

	def on_toplevel_synced(self, context, toplevel):
		# Obviously this should do a proper diff and only update if required
		toplevel.button.set_label(toplevel.title)
		if 'activated' in toplevel.states:
			if toplevel.button != self.active_button:
				if self.active_button:
					style = self.active_button.get_style_context()
					style.remove_class('activated')
				style = toplevel.button.get_style_context()
				style.add_class('activated')
				self.active_button = toplevel.button
		elif toplevel.button == self.active_button:
			style = toplevel.button.get_style_context()
			style.remove_class('activated')

	def on_toplevel_closed(self, context, toplevel):
		self.box.remove(toplevel.button)

	def on_periodic_update(self, context):
		self.clock.set_label(datetime.datetime.now().strftime('%a %b %-d, %H:%M'))

	def handle_scroll(self, scroll, event):
		adj = scroll.get_hadjustment()
		if adj.get_upper() <= adj.get_page_size():
			return
		val = adj.get_value()
		if event.direction == Gdk.ScrollDirection.UP or event.delta_y < 0:
			if val > adj.get_lower():
				adj.set_value(val - adj.get_minimum_increment())
		elif event.direction == Gdk.ScrollDirection.DOWN or event.delta_y > 0:
			if val + adj.get_page_size() < adj.get_upper():
				adj.set_value(val + adj.get_minimum_increment())

	def handle_context_menu(self, button, event, toplevel):
		if event.button != Gdk.BUTTON_SECONDARY:
			return False
		for menu, func in (
			(self._menu_maximize, self.manager.app_toggle_maximize),
			(self._menu_minimize, self.manager.app_toggle_minimize),
			(self._menu_fullscreen, self.manager.app_toggle_fullscreen),
			(self._menu_close, self.manager.app_close)
		):
			try:
				menu.disconnect_by_func(func)
			except TypeError:
				pass
			menu.connect('activate', func, toplevel)
		self._menu_maximize.set_label(
			'UnMaximize' if 'maximized' in toplevel.states else 'Maximize')
		self._menu_minimize.set_label(
			'UnMinimize' if 'minimized' in toplevel.states else 'Minimize')
		self._menu_fullscreen.set_label(
			'UnFullscreen' if 'fullscreen' in toplevel.states else 'Fullscreen')
		self.menu.popup_at_widget(button, Gdk.Gravity.NORTH, Gdk.Gravity.SOUTH, event)
		return True

	def _create_scroll(self):
		self.scroll = Gtk.ScrolledWindow()
		self.scroll.set_policy(
			Gtk.PolicyType.EXTERNAL,
			Gtk.PolicyType.NEVER
		)
		self.box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
		self.box.set_name('tasklist')
		self.scroll.add(self.box)
		self.scroll.connect('scroll-event', self.handle_scroll)
		self.scroll.show_all()
		return self.scroll

	def _create_clock(self):
		self.clock = Gtk.Label(label='some clock')
		self.clock.set_name('clock')
		self.clock.set_valign(0.5)
		self.on_periodic_update(None)
		return self.clock

	def _create_menu(self):
		menu = Gtk.Menu.new()
		menu.set_name('panel_menu')
		self._menu_maximize = Gtk.MenuItem.new_with_label('Maximize')
		self._menu_minimize = Gtk.MenuItem.new_with_label('Minimize')
		self._menu_fullscreen = Gtk.MenuItem.new_with_label('Fullscreen')
		self._menu_close = Gtk.MenuItem.new_with_label('Close')

		menu.append(self._menu_maximize)
		menu.append(self._menu_minimize)
		menu.append(self._menu_fullscreen)
		menu.append(Gtk.SeparatorMenuItem())
		menu.append(self._menu_close)

		menu.show_all()
		self.menu = menu
		return menu

	def _add_style(self):
		self.css_provider = Gtk.CssProvider()
		self.css_provider.load_from_data(b'''
			#panel #clock {
				font-family: monospace;
			}
			#panel #tasklist button.activated label {
				font-weight: bold;
			}
			#panel #tasklist button:hover,
			#panel #tasklist button.activated {
				box-shadow: 0px 0px 5px rgba(128, 128, 128, 0.7) inset;
			}
			#panel_menu {
				border-radius: 0;
			}
		''')
		screen = Gdk.Screen.get_default()
		context = Gtk.StyleContext()
		context.add_provider_for_screen(screen, self.css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


if __name__ == '__main__':

	import sys

	try:
		context = Context()
	except RuntimeError as e:
		print(e)
		sys.exit(1)

	panel = PanelWindow(context)
	panel.set_size_request(-1, 26)
	GtkLayerShell.init_for_window(panel)
	GtkLayerShell.auto_exclusive_zone_enable(panel)
	GtkLayerShell.set_anchor(panel, GtkLayerShell.Edge.LEFT, True)
	GtkLayerShell.set_anchor(panel, GtkLayerShell.Edge.RIGHT, True)
	GtkLayerShell.set_anchor(panel, GtkLayerShell.Edge.BOTTOM, True)
	GtkLayerShell.set_layer(panel, GtkLayerShell.Layer.BOTTOM)
	panel.show_all()

	try:
		Gtk.main()
	except KeyboardInterrupt:
		print()
