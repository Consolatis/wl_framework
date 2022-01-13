# https://gitlab.freedesktop.org/wayland/wayland/-/blob/main/protocol/wayland.xml

import struct

from .base import (
	ArgUint32,
	ArgString,
	Interface
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
		connection.add_event_handler(self)
		self.add_event(self.on_error)
		self.add_event(self.on_delete_id)
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
		self._initial_sync = False
		self.add_event(self.on_global)
		self.add_event(self.on_global_remove)

	# Wayland events
	def on_global(self, data, fds):
		name, version, global_id = ArgRegistryGlobal.parse(data)
		self._registry[name] = (global_id, version)

	def on_global_remove(self, data, fds):
		_, global_id = ArgUint32.parse(data)
		# FIXME: should destroy all object instances for this global_id
		if global_id not in self._registry:
			self.log(f"Can't remove global id {global_id}: We have no idea about it")
			return
		del self._registry[global_id]
		self.log(f"Not destroying instances of global id {global_id}")

	# Wayland methods
	def do_bind(self, interface):
		if not self._initial_sync:
			raise RuntimeError("Bind without waiting for full sync. Please bind in on_initial_sync().")
		if interface.name not in self._registry:
			raise RuntimeError(f"Interface {interface.name} not supported by server")
		global_id, version = self._registry[interface.name]
		version = min(interface.version, version)
		if version < interface.version:
			interface.set_version(version)
		interface.obj_id = self.get_new_obj_id()
		data = ArgRegistryBind.create(global_id, interface.name, version, interface.obj_id)
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
