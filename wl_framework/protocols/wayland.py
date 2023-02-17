# https://gitlab.freedesktop.org/wayland/wayland/-/blob/main/protocol/wayland.xml

import struct
from collections import defaultdict

from .base import (
	ArgUint32,
	ArgString,
	Interface,
	UnsupportedProtocolError
)

class ArgDisplayError:
	def parse(data):
		oid, code = struct.unpack('=II', data[:8])
		_, msg = ArgString.parse(data[8:])
		return (oid, code, msg)

class ArgRegistryGlobal:
	def parse(data):
		global_id = struct.unpack('=I', data[:4])[0]
		data = data[4:]
		consumed, interface = ArgString.parse(data)
		data = data[consumed:]
		version = struct.unpack('=I', data)[0]
		return (interface, version, global_id)

class ArgRegistryBind:
	def create(global_id, name, version, new_obj_id):
		data =  ArgUint32.create(global_id)
		data += ArgString.create(name)
		data += ArgUint32.create(version)
		data += ArgUint32.create(new_obj_id)
		return data

class Display(Interface):
	def __init__(self, connection):
		super().__init__(connection)
		self.obj_id = 1
		self.set_name('wl_display')
		self.set_version(1)
		self.add_event(self.on_error)
		self.add_event(self.on_delete_id)
		connection.add_event_handler(self)
		self.registry = self.get_registry()

	# Wayland events
	def on_error(self, data, fds):
		obj_id, err_code, err_msg = ArgDisplayError.parse(data)
		obj = self._connection.get_obj(obj_id)
		self.log(f"Got Display error for {obj or obj_id}: [{err_code}] {err_msg}")

	def on_delete_id(self, data, fds):
		_, obj_id = ArgUint32.parse(data)
		self._connection.free_obj_id(obj_id)

	# Wayland methods
	def do_sync(self, callback):
		sync_id = self.get_new_obj_id()
		self._connection.add_event_handler(sync_id, callback)
		data = ArgUint32.create(sync_id)
		self.send_command(0, data)

	def get_registry(self):
		registry = Registry(self._connection, self.get_new_obj_id())
		self._connection.add_event_handler(registry)
		data = ArgUint32.create(registry.obj_id)
		self.send_command(1, data)
		return registry

	# Internal events
	def on_initial_sync(self):
		self.seat = Seat(self._connection)


class Registry(Interface):
	def __init__(self, connection, obj_id):
		super().__init__(connection, obj_id=obj_id)
		self.set_name('wl_registry')
		self.set_version(1)
		self._registry = dict()
		self._interfaces = defaultdict(list)
		self._initial_sync = False
		self.add_event(self.on_global)
		self.add_event(self.on_global_remove)

	# Wayland events
	def on_global(self, data, fds):
		name, version, global_id = ArgRegistryGlobal.parse(data)
		if global_id in self._registry:
			self.log(f"Got multiple globals for the same id {global_id}: {name} v{version}")
			return
		self._registry[global_id] = (name, version)
		self._interfaces[name].append(global_id)

	def on_global_remove(self, data, fds):
		_, global_id = ArgUint32.parse(data)
		if global_id not in self._registry:
			self.log(f"Can't remove global id {global_id}: We don't know anything about it")
			return
		name, version = self._registry.pop(global_id)
		self._interfaces[name].remove(global_id)
		if len(self._interfaces[name]) == 0:
			del self._interfaces[name]

		# TODO: Should we notify all current instances of this global?

	# Wayland methods
	def do_bind(self, interface, ignore_sync=False):
		if not self._initial_sync and not ignore_sync:
			raise RuntimeError("Bind without waiting for full sync. Please bind in on_initial_sync().")

		if interface.iface_name not in self._interfaces:
			raise UnsupportedProtocolError(f"Interface {interface.iface_name} not supported by server")

		global_id = interface.global_id
		if global_id is None:
			global_id = self._interfaces[interface.iface_name][0]

		if global_id not in self._registry:
			raise ValueError(f"global_id {global_id} specified but not found in registry")

		name, version = self._registry[global_id]
		version = min(interface.version, version)
		if version < interface.version:
			interface.set_version(version)
		interface.obj_id = self.get_new_obj_id()
		data = ArgRegistryBind.create(global_id, interface.iface_name, version, interface.obj_id)
		self.send_command(0, data)

	# Internal events
	def on_initial_sync(self):
		self._initial_sync = True

class Seat(Interface):
	def __init__(self, connection):
		super().__init__(connection)
		self.set_name('wl_seat')
		self.set_version(7)
		self.add_event(self.on_capabilities)
		self.add_event(self.on_name)
		self.bind()

	# Wayland events
	def on_capabilities(self, data, fds):
		pass

	def on_name(self, data, fds):
		pass

	# Wayland methods
	def get_keyboard(self):
		pass

	def get_touch(self):
		pass

	def release(self):
		if self.version < 5:
			return
		pass
