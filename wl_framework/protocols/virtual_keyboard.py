# https://gitlab.freedesktop.org/wlroots/wlroots/-/blob/master/protocol/virtual-keyboard-unstable-v1.xml
# https://gitlab.freedesktop.org/wayland/wayland-protocols/-/merge_requests/11

import os
import time
from contextlib import contextmanager

from .base import ArgUint32, Interface
from ._keymap import KeyMap

WL_KEYBOARD_KEY_STATE_PRESSED = 1
WL_KEYBOARD_KEY_STATE_RELEASED = 0
WL_KEYBOARD_KEYMAP_FORMAT_XKB_V1 = 1

class VirtualKeyboardManager(Interface):

	def __init__(self, connection):
		super().__init__(connection)
		self.set_name('zwp_virtual_keyboard_manager_v1')
		self.set_version(1)
		self.bind()

	# Wayland requests
	def create_virtual_keyboard(self, seat):
		kb = VirtualKeyboard(self._connection)
		data = ArgUint32.create(seat.obj_id)
		data += ArgUint32.create(kb.obj_id)
		self.send_command(0, data)
		return kb

class VirtualKeyboard(Interface):
	# What are MOD_UNKWN_{1,2}? 16 / 32
	MOD_NONE = 0
	MOD_SHIFT,    \
	MOD_CAPSLOCK, \
	MOD_CTRL,     \
	MOD_ALT,      \
	MOD_UNKWN_1,  \
	MOD_UNKWN_2,  \
	MOD_LOGO,     \
	MOD_ALTGR = tuple((1 << x) for x in range(8))

	def __init__(self, connection):
		super().__init__(connection)
		self.obj_id = self.get_new_obj_id()
		self.set_name('zwp_virtual_keyboard_v1')
		self.set_version(1)

		self._keymap = KeyMap(log_fn=self.__class__.log)
		self._modifiers = self.MOD_NONE
		self._write_delay = 0

	# API
	def set_write_delay(self, delay):
		self._write_delay = delay

	def write(self, text, sleep_s=0):
		keys = self._keymap.get_keys(text)
		self._update_keymap()
		for key in keys:
			self.key(key, WL_KEYBOARD_KEY_STATE_PRESSED)
			self.key(key, WL_KEYBOARD_KEY_STATE_RELEASED)
			if sleep_s:
				time.sleep(sleep_s)
			elif self._write_delay:
				time.sleep(self._write_delay)

	def send_key(self, key, sleep_s=0):
		try:
			key = self._keymap.get_key(key)
			self._update_keymap()
			self.key(key, WL_KEYBOARD_KEY_STATE_PRESSED)
			self.key(key, WL_KEYBOARD_KEY_STATE_RELEASED)
			if sleep_s:
				time.sleep(sleep_s)
			elif self._write_delay:
				time.sleep(self._write_delay)
		except Exception as e:
			self.log(e)

	@contextmanager
	def modifier(self, modifier):
		# We have to ensure a keymap is set before
		# setting modifiers. This is usually a no-op.
		self._update_keymap()

		self._modifiers |= modifier
		self._update_modifiers()
		yield self
		self._modifiers &= ~modifier
		self._update_modifiers()

	# Internal helpers
	def _update_keymap(self):
		if not self._keymap.changed:
			return
		keymap = self._keymap.serialize().encode()
		# TODO: Verify this works for the BSDs as well, otherwise fall back to tempfile
		fd = os.memfd_create('tmp-keymap')
		os.ftruncate(fd, len(keymap))
		os.write(fd, keymap)
		try:
			self.keymap(fd, len(keymap))
			self._keymap.changed = False
		finally:
			os.close(fd)

	def _update_modifiers(self):
		depressed = self._modifiers & ~self.MOD_CAPSLOCK
		latched = self.MOD_NONE
		locked = self._modifiers & self.MOD_CAPSLOCK
		group = 0
		self.modifiers(depressed, latched, locked, group)

	# Wayland requests
	def keymap(self, fd, size):
		data = ArgUint32.create(WL_KEYBOARD_KEYMAP_FORMAT_XKB_V1)
		data += ArgUint32.create(size)
		self.send_command(0, data, (fd,))

		# Updating the keymap seems to reset the modifier state
		if self._modifiers:
			self._update_modifiers()

	def key(self, key, state):
		ms = int(time.monotonic() * 1000)
		data = ArgUint32.create(ms % (2**32))
		data += ArgUint32.create(key)
		data += ArgUint32.create(state)
		self.send_command(1, data)

	def modifiers(self, depressed, latched, locked, group):
		data = ArgUint32.create(depressed)
		data += ArgUint32.create(latched)
		data += ArgUint32.create(locked)
		data += ArgUint32.create(group)
		self.send_command(2, data)

	def destroy(self):
		self.send_command(3)

if __name__ == '__main__':
	keymap = KeyMap()
	keys = keymap.get_keys("H€llo, is this ä ŧæſðđŋħst?")
	print("Got keys:", keys)
	print(keymap.serialize())
