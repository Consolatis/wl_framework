# FIXME: for all of wl_framework (likely Interface): add something like set_factory_classes({'name': some_class})
#        + initialize those in __init__ to default values and then use those for creating new instances

import struct

class ArgString:
	def parse(data):
		size = struct.unpack('=I', data[:4])[0]
		data = data[4:4 + size - 1]
		padding = (4 - (size % 4)) % 4
		return 4 + size + padding, data.decode()
	def create(data):
		if isinstance(data, str):
			data = data.encode('utf-8')
		size = len(data) + 1
		# always enforces at least one \x00 at the end as it will add 4 on % 4 == 0
		data = struct.pack('=I', size) + data + (b'\x00' * (4 - (len(data) % 4)))
		return data

class ArgInt32:
	def parse(data):
		return 4, struct.unpack('=i', data[:4])[0]
	def create(val):
		return struct.pack('=i', val)

class ArgUint32:
	def parse(data):
		return 4, struct.unpack('=I', data[:4])[0]
	def create(val):
		return struct.pack('=I', val)

class ArgArray:
	def parse(data):
		size = struct.unpack('=I', data[:4])[0]
		data = data[4:4 + size]
		return 4 + size, data

class UnsupportedProtocolError(Exception):
	pass

class Interface:
	def __init__(self, connection, obj_id=None):
		self.version = 1
		self._events = list()
		self._connection = connection
		self.obj_id = obj_id
		self.iface_name = None
		self.global_id = None

	def no_op(self, *args, **kwargs):
		pass

	def set_name(self, name):
		self.iface_name = name

	def set_version(self, version):
		self.version = version

	def add_event(self, callback):
		self._events.append(callback)

	def get_new_obj_id(self):
		return self._connection.get_new_obj_id()

	def sync(self, callback):
		self._connection.sync(callback)

	def bind(self):
		self._connection.bind(self)

	def on_initial_sync(self):
		pass

	def on_destroyed(self):
		pass

	def send_command(self, opcode, data=b'', fds=None):
		self._connection.send_opcode(self.obj_id, opcode, data, fds)

	def log(self, *msg):
		name = f"[{self.__class__.__name__}]"
		print(f" {name:^25s} ", *msg)

	def __repr__(self):
		return f'<{self.iface_name}-{self.obj_id}>'

	def __hash__(self):
		return self.obj_id
