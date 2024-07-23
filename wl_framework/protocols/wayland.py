# https://gitlab.freedesktop.org/wayland/wayland/-/blob/main/protocol/wayland.xml

import struct
from collections import defaultdict

from .base import (
	ArgInt32,
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
		self.outputs = list()

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
		self.shm = Shm(self._connection)

	def on_output_new(self, output):
		self.outputs.append(output)

	def on_output_del(self, output_global):
		for output in tuple(self.outputs):
			if output.global_id == output_global:
				self.outputs.remove(output)
				self.log(f"Output {output_global} removed, {len(self.outputs)} outputs remaining")
				return
		self.log(f"We can't remove output {output_global} because we don't know anything about it")

	def get_output_by_id(self, output_id):
		for output in self.outputs:
			if output.obj_id == output_id:
				return output
		raise Exception(f"No output with id {output_id}")

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

		if name == 'wl_output':
			#self.log("Creating new output:", global_id, "with server supported version", version)
			output = Output(self._connection, global_id)
			self.do_bind(output, ignore_sync=True)
			self._connection.add_event_handler(output)
			self._connection.display.on_output_new(output)

	def on_global_remove(self, data, fds):
		_, global_id = ArgUint32.parse(data)
		if global_id not in self._registry:
			self.log(f"Can't remove global id {global_id}: We don't know anything about it")
			return
		name, version = self._registry.pop(global_id)
		self._interfaces[name].remove(global_id)
		if len(self._interfaces[name]) == 0:
			del self._interfaces[name]

		if name == 'wl_output':
			self._connection.display.on_output_del(global_id)

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

class Output(Interface):
	MODE_CURRENT = 1
	MODE_PREFERRED = 2
	def __init__(self, connection, global_id):
		super().__init__(connection)
		self.set_name('wl_output')
		self.set_version(4)
		self.global_id = global_id
		self._events = (
			self.on_geometry,
			self.on_mode,
			self.on_done,
			self.on_scale,
			self.on_name,
			self.on_description
		)
		self.width = 0
		self.height = 0
		self.name = None
		self.description = None

	# Wayland events
	def on_geometry(self, data, fds):
		offset = 0
		consumed, x = ArgInt32.parse(data[offset:])
		offset += consumed
		consumed, y = ArgInt32.parse(data[offset:])
		offset += consumed
		consumed, w_phys = ArgInt32.parse(data[offset:])
		offset += consumed
		consumed, h_phys = ArgInt32.parse(data[offset:])
		offset += consumed
		consumed, sub = ArgInt32.parse(data[offset:])
		offset += consumed
		consumed, make = ArgString.parse(data[offset:])
		offset += consumed
		consumed, model = ArgString.parse(data[offset:])
		offset += consumed
		_, transform = ArgInt32.parse(data[offset:])

		#self.log(f"on_geometry (version {self.version}): pos {x}|{y} phys {w_phys}x{h_phys} subpixel align {sub} {model} from {make} with transform {transform}")

	def on_mode(self, data, fds):
		_, _flags = ArgUint32.parse(data)
		_, width = ArgInt32.parse(data[4:])
		_, height = ArgInt32.parse(data[8:])
		_, refresh = ArgInt32.parse(data[12:])
		flags = list()
		if _flags & Output.MODE_CURRENT:
			self.width = width
			self.height = height
			flags.append('current')
		if _flags & Output.MODE_PREFERRED:
			flags.append('preferred')
		flags = ', '.join(flags)
		#self.log(f"on_mode (version {self.version}): {width}x{height}@{refresh} {flags}")

	def on_done(self, data, fds):
		#self.log("on_done")
		pass

	def on_scale(self, data, fds):
		#self.log("on_scale")
		pass

	def on_name(self, data, fds):
		_, name = ArgString.parse(data)
		self.name = name
		#self.log("Got name:", name)

	def on_description(self, data, fds):
		_, description = ArgString.parse(data)
		self.description = description
		#self.log("Got description:", description)

	def __repr__(self):
		return f'{self.__class__.__name__}-{self.global_id}'

class Shm(Interface):
	def __init__(self, connection):
		super().__init__(connection)
		self.set_name('wl_shm')
		self.set_version(1)
		self.add_event(self.on_format)
		self._formats = set()
		self.bind()

	# Wayland events
	def on_format(self, data, fds):
		_, format = ArgUint32.parse(data)
		#self.log("Got SHM format:", format)
		self._formats.add(format)

	# Wayland methods
	def create_pool(self, fd, size):
		pool = ShmPool(self._connection, self._formats, size)
		data = ArgUint32.create(pool.obj_id)
		data += ArgUint32.create(size)
		self.send_command(0, data, fd)
		return pool

class ShmPool(Interface):
	def __init__(self, connection, shm_formats, size):
		super().__init__(connection)
		self.set_name('wl_shm_pool')
		self.set_version(1)
		self.obj_id = connection.get_new_obj_id()
		connection.add_event_handler(self)
		self._shm_formats = shm_formats
		self._size = size

	# Wayland methods
	def create_buffer(self, offset, width, height, stride, format):
		if format not in self._shm_formats:
			raise ValueError(f"Format {format} not supported by compositor")

		req_size = height * stride
		if offset + req_size > self._size:
			raise ValueError(f"Offset {offset} + buffer_size {req_size} > pool size of {self._size}")

		buffer = WlBuffer(self._connection)
		data = ArgUint32.create(buffer.obj_id)
		data += ArgInt32.create(offset)
		data += ArgInt32.create(width)
		data += ArgInt32.create(height)
		data += ArgInt32.create(stride)
		data += ArgUint32.create(format)
		self.send_command(0, data)
		return buffer

	def destroy(self):
		self.send_command(1)

	def resize(self, new_size):
		data = ArgInt32.create(new_size)
		self.send_command(2, data)

class WlBuffer(Interface):
	def __init__(self, connection):
		super().__init__(connection)
		self.set_name('wl_buffer')
		self.set_version(1)
		self.obj_id = connection.get_new_obj_id()
		connection.add_event_handler(self)
		self.add_event(self.on_release)

	# Wayland events
	def on_release(self, data, fds):
		#self.log("Buffer released")
		pass

	# Wayland methods
	def destroy(self):
		self.send_command(0)
