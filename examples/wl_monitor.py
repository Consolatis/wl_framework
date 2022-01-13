#!/usr/bin/env python3

from functools import partial

from wl_framework.network.connection import WaylandConnection
from wl_framework.protocols.foreign_toplevel import ForeignTopLevel
from wl_framework.protocols.data_control import DataControl

class ForeignTopLevelMonitor(ForeignTopLevel):

	def on_toplevel_created(self, toplevel):
		self.log(f"New toplevel created: @{toplevel.obj_id}")

	def on_toplevel_synced(self, toplevel):
		self.log(f"Topevel @{toplevel.obj_id} state synced:")
		for property in ('app_id', 'title', 'states'):
			val = getattr(toplevel, property)
			if property == 'states':
				val = ', '.join(x.capitalize() for x in val) if val else '-'
			self.log(f"  {property.capitalize():6s}  {val}")

	def on_toplevel_closed(self, toplevel):
		self.log(f"Toplevel closed: {toplevel}")


class ClipboardMonitor(DataControl):

	def on_new_selection(self, offer):
		self._print_selection(offer)
		self._receive(offer)

	def on_new_primary_selection(self, offer):
		self._print_selection(offer, is_primary=True)
		self._receive(offer, is_primary=True)

	# Internal
	def _receive(self, offer, is_primary=False):
		if offer is None:
			return
		for mime in (
			'text/plain;charset=utf-8',
			'UTF8_STRING',
		):
			if mime in offer.get_mime_types():
				offer.receive(mime, partial(self._on_received, is_primary=is_primary))
				break

	def _print_selection(self, offer, is_primary=False):
		_selection = 'primary' if is_primary else 'main'
		if offer is None:
			self.log(f"{_selection.capitalize()} selection cleared")
			return
		self.log(f"New {_selection} selection offers:")
		for mime_type in offer.get_mime_types():
			self.log(f"  {mime_type}")

	def _on_received(self, mime_type, data, is_primary=False):
		if data:
			data = data.decode('utf-8')
		self.log(f"Received {' primary' if is_primary else 'main'} selection: '{data}'")


class WlMonitor(WaylandConnection):

	def on_initial_sync(self, data):
		super().on_initial_sync(data)
		self.toplevels = ForeignTopLevelMonitor(self)
		self.clipboard = ClipboardMonitor(self)


if __name__ == '__main__':

	import sys
	run_async = False

	if run_async:
		import asyncio
		from wl_framework.loop_integrations import AsyncIOIntegration

		async def init():
			loop = AsyncIOIntegration()
			try:
				app = WlMonitor(eventloop_integration=loop)
				while True:
					await asyncio.sleep(3600)
			except RuntimeError as e:
				print(e)
				sys.exit(1)
		try:
			asyncio.run(init())
		except KeyboardInterrupt:
			print()

	else:

		from wl_framework.loop_integrations import PollIntegration
		loop = PollIntegration()

		try:
			app = WlMonitor(eventloop_integration=loop)
		except RuntimeError as e:
			print(e)
			sys.exit(1)
		try:
			loop.run()
		except KeyboardInterrupt:
			print()
