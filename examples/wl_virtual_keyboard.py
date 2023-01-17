#!/usr/bin/env python3

from wl_framework.network.connection import WaylandConnection, WaylandDisconnected
from wl_framework.protocols.virtual_keyboard import VirtualKeyboardManager

class WlVirtualKeyboard(WaylandConnection):

	def on_initial_sync(self, data):
		super().on_initial_sync(data)
		self.manager = VirtualKeyboardManager(self)
		self.keyboard = self.manager.create_virtual_keyboard(self.display.seat)

		# Just looks nicer
		self.keyboard.set_write_delay(0.1)

		# Unicode test
		self.keyboard.write("H€lłø, is đħis ä … ŧæst ¿\n¥€$ 😊\n\n")

		# Special key test
		self.keyboard.write("World")
		self.keyboard.send_key("home")
		self.keyboard.write("Hello ")
		self.keyboard.send_key("end")
		self.keyboard.write("!\n\n")

		# Modifier test
		with self.keyboard.modifier(self.keyboard.MOD_LOGO):
			self.keyboard.send_key("a")

		self.sync(self.on_done)

	def on_done(self, data):
		self.shutdown()

if __name__ == '__main__':

	import sys
	import time

	def usage_and_die():
		print(
			"\n\x1b[1mWarning\x1b[m: This example will inject key events.\n" +
			"It has to be called with a --delay argument like\n\n" +
			f"\"{sys.argv[0]} --delay 5\"\n\n" +
			"to provide enough time to switch to a text editor like nano."
		)
		exit(0)

	if len(sys.argv) != 3 or sys.argv[1] != '--delay':
		usage_and_die()
	try:
		time.sleep(int(sys.argv[2]))
	except:
		usage_and_die()

	from wl_framework.loop_integrations import PollIntegration
	loop = PollIntegration()

	try:
		app = WlVirtualKeyboard(eventloop_integration=loop)
		loop.run()
	except RuntimeError as e:
		print(e)
		exit(1)
	except KeyboardInterrupt:
		print()
	except WaylandDisconnected:
		pass
