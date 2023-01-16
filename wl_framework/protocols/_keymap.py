# Helper class for virtual_keyboard.py

import ctypes
import string
from functools import partial

XKB_KEY_NoSymbol = 0
XKB_KEYSYM_CASE_INSENSITIVE = 1

class KeyMap:
	def __init__(self, log_fn=None, prime=False):
		self._map = dict()

		if prime:
			self._prime()

		if log_fn:
			self.log = partial(log_fn, self)
		else:
			self.log = print

		try:
			self.lib = ctypes.cdll.LoadLibrary('libxkbcommon.so')
			self._get_symbol = self._get_symbol_xkb
		except OSError as e:
			self.log(e)
			self.log("Falling back to internal parser, some symbol names may not work")
			self._get_symbol = self._get_symbol_no_xkb

		self.changed = True

	def _prime(self):
		# Prime ASCII
		for char in ' ' + string.ascii_letters + string.punctuation:
			self._map[char] = (len(self._map) + 1, ord(char))

	def get_symbol(self, name):
		symbol = {
			'\t': 0xff09, # XKB_KEY_Tab
			'\n': 0xff0d, # XKB_KEY_Return
		}.get(name, None)
		if not symbol:
			symbol = self._get_symbol(name)

		#self.log(f"'{name}' -> {symbol} {f'(U+{symbol:02x})' if isinstance(symbol, int) else ''}")
		return symbol

	def _get_symbol_xkb(self, name):
		if len(name) == 1:
			res = self.lib.xkb_utf32_to_keysym(ord(name));
		else:
			res = self.lib.xkb_keysym_from_name(name.encode(), XKB_KEYSYM_CASE_INSENSITIVE)

		if res == XKB_KEY_NoSymbol:
			raise Exception(f"Failed to find proper symbol for '{name}'")
		return res

	def _get_symbol_no_xkb(self, name):
		if len(name) == 1:
			symbol = ord(name)
			if symbol >= 0x20 and symbol <= 0x7e:
				# legacy ASCII
				return symbol
			elif symbol >= 0xa0 and symbol <= 0x10ffff:
				# /usr/include/xkbcommon/xkbcommon-keysyms.h L100-106
				return f'U{symbol:x}'
			else:
				# C0 or C1 control keyspace or unsupported high unicode point
				pass
		else:
			# TODO: Missing further numpad keys, function keys
			symbol = {
				# /usr/include/xkbcommon/xkbcommon-keysyms.h L130-139
				'backspace':   0xff08,
				'tab':         0xff09,
				'linefeed':    0xff0a,
				'clear':       0xff0b,
				'return':      0xff0d,
				'pause':       0xff13,
				'scroll_lock': 0xff14,
				'sys_req':     0xff15,
				'escape':      0xff1b,
				'delete':      0xffff,
				# /usr/include/xkbcommon/xkbcommon-keysyms.h L178-188
				'home':        0xff50,
				'left':        0xff51,
				'up':          0xff52,
				'right':       0xff53,
				'down':        0xff54,
				'prior':       0xff55,
				'page_up':     0xff55,
				'next':        0xff56,
				'page_down':   0xff56,
				'end':         0xff57,
				'begin':       0xff58,
				# /usr/include/xkbcommon/xkbcommon-keysyms.h L193-206 (with a few left out)
				'print':       0xff61,
				'insert':      0xff63,
				'undo':        0xff65,
				'redo':        0xff66,
				'menu':        0xff67,
				'find':        0xff68,
				'cancel':      0xff69,
				'help':        0xff6a,
				'break':       0xff6b,
				'num_lock':    0xff7f,
				# /usr/include/xkbcommon/xkbcommon-keysyms.h L238-247
				'kp_0':        0xffb0,
				'kp_1':        0xffb1,
				'kp_2':        0xffb2,
				'kp_3':        0xffb3,
				'kp_4':        0xffb4,
				'kp_5':        0xffb5,
				'kp_6':        0xffb6,
				'kp_7':        0xffb7,
				'kp_8':        0xffb8,
				'kp_9':        0xffb9,
			}.get(name, None)
			if symbol:
				return symbol

		raise Exception(f"Failed to find proper symbol for '{name}'")

	def get_key(self, key):
		if len(key) > 1:
			key = key.lower()
		key_sym = self._map.get(key, None)
		if key_sym is None:
			key_sym = (len(self._map) + 1, self.get_symbol(key))
			self._map[key] = key_sym
			self.changed = True
		return key_sym[0]

	def get_keys(self, text):
		res = list()
		for char in text:
			key_sym = self._map.get(char, None)
			try:
				if key_sym is None:
					key_sym = (len(self._map) + 1, self.get_symbol(char))
					self._map[char] = key_sym
					self.changed = True
				res.append(key_sym[0])
			except Exception as e:
				self.log(e)
		return res

	def _generate(self):
		# Thanks to https://github.com/atx/wtype for giving hints of the required format
		yield 'xkb_keymap {'
		yield '  xkb_keycodes "virt_map" {'
		yield '    minimum = 8;'
		yield f'    maximum = {8 + len(self._map)};'
		for _id, symbol in self._map.values():
			yield f'    <K{_id}> = {_id + 8};'
		yield '  };'
		yield '  xkb_types "virt_map" { include "complete" };'
		yield '  xkb_compatibility "virt_map" { include "complete" };'
		yield '  xkb_symbols "virt_map" {'
		for _id, symbol in self._map.values():
			yield f'    key <K{_id}> {{ [ {symbol} ] }};'
		yield '  };'
		yield '};'

	def serialize(self):
		return '\n'.join(self._generate())
