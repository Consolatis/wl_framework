#!/usr/bin/env python3

from wl_framework.network.connection import (
	WaylandConnection,
	WaylandDisconnected
)
from wl_framework.protocols.foreign_toplevel import ForeignTopLevel

class WlCtrl(WaylandConnection):
	def __init__(self, sys_args, *args, **kwargs):
		if not sys_args:
			self.action = 'list'
		else:
			actions = {
				       'focus': ('activate', None),
				    'activate': ('activate', None),
				    'maximize': ('set_maximize', (True,)),
				    'minimize': ('set_minimize', (True,)),
				  'fullscreen': ('set_fullscreen', (True,)),
				  'unmaximize': ('set_maximize', (False,)),
				  'unminimize': ('set_minimize', (False,)),
				'unfullscreen': ('set_fullscreen', (False,)),
				       'close': ('close', tuple())
			}
			self.target = sys_args[0]
			self.action = actions.get(sys_args[1])
			if (
				not self.action
				or not self.target
				or self.target[0] not in '#@=:'
				or len(self.target) < 2
			):
				raise RuntimeError(usage)
		super().__init__(*args, **kwargs)

	def quit(self, data=None):
		self.shutdown()

	def on_initial_sync(self, data):
		super().on_initial_sync(data)
		if self.action[0] == 'activate':
			# As we are subclassing the connection itself
			# we have to patch the action here because
			# the seat is only set in this very function.
			self.action = ('activate', (self.display.seat,))
		self.toplevels = ForeignTopLevel(self)
		# ForeignTopLevel will .bind() in its constructor
		# which will then cause the server to send all of
		# the initial toplevel states. Thus we just wait
		# for that to happen by queueing a callback and
		# then looping over the results.
		self.sync(self.info_done)

	def info_done(self, data):
		if self.action == 'list':
			self._print_list()
			self.quit()
			return

		target_matches = {
			'#': lambda window, target : int(target[1:]) == window.obj_id,
			'@': lambda window, target : target[1:].lower() == window.app_id.lower(),
			'=': lambda window, target : target[1:].lower() == window.title.lower(),
			':': lambda window, target : target[1:].lower() in window.title.lower()
		}.get(self.target[0])

		windows_found = list()
		for window in self.toplevels.windows.values():
			if target_matches(window, self.target):
				windows_found.append(window)
		if not windows_found:
			print(f"No window matches target {self.target}")
			self.quit()
			return
		if len(windows_found) > 1:
			print(f"Found multiple windows. Not doing anything.")
			self._print_list(windows_found)
			self.quit()
			return
		func_name, func_args = self.action
		func = getattr(windows_found[0], func_name)
		func(*func_args)
		# Wait for roundtrip to return before closing the connection
		self.sync(self.quit)

	def _print_list(self, windows=None):
		if windows is None:
			windows = self.toplevels.windows.values()
		if not windows:
			print("No windows opened")
			self.quit()
			return
		class d:
			obj_id = ' Handle'
			app_id = ' AppID'
			title = ' Title'
		handle_max = max(len(d.obj_id), max(len(str(x.obj_id)) for x in windows))
		app_id_max = max(len(d.app_id), max(len(x.app_id) for x in windows))
		title_max = max(len(d.title), max(len(x.title) for x in windows))
		fmt = "  {0.obj_id:{1}}    {0.app_id:{2}}    {0.title:{3}}"
		print()
		print(fmt.format(d, handle_max, app_id_max, title_max))
		print("  {:-<{}}    {:-^{}}    {:->{}}".format('', handle_max, '', app_id_max, '', title_max))
		for window in windows:
			print(fmt.format(window, handle_max, app_id_max, title_max))
		print()

if __name__ == '__main__':

	import sys
	from wl_framework.loop_integrations import PollIntegration

	usage = \
f"""

	Usage: {sys.argv[0]} [<window-handle> <action>]

	Without arguments: List windows

	<window-handle> should be one of:
		#handle   match handle
		@app_id   match app_id
		=title    match title
		:title    match part of title
		Warning: #window-handle might be reused or differ completely on the next call!

	<action> should be one of:
		activate | focus
		close
		maximize
		minimize
		fullscreen
		unmaximize
		unminimize
		unfullscreen
"""
	if len(sys.argv) not in (1, 3):
		print(usage)
		sys.exit(1)

	loop = PollIntegration()

	try:
		app = WlCtrl(sys.argv[1:], eventloop_integration=loop)
	except RuntimeError as e:
		print(e)
		sys.exit(1)

	try:
		loop.run()
	except WaylandDisconnected:
		pass
