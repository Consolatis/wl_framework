import os
import errno
import array
import socket
import struct

from ..protocols.base import Interface
from ..protocols.wayland import Display
from ..loop_integrations.dummy import DummyIntegration

class WaylandDisconnected(Exception):
	pass

# TODO: cleanup and use sections
class WaylandConnection:
	def __init__(self, eventloop_integration=None):
		self._obj_ids_reuse = list()
		self._obj_ids = self._obj_id_generator()

		xdg_runtime_dir = os.getenv('XDG_RUNTIME_DIR', None)
		wayland_display = os.getenv('WAYLAND_DISPLAY', None)
		if None in (xdg_runtime_dir, wayland_display):
			raise RuntimeError(
				"Requires wayland environment variables set: XDG_RUNTIME_DIR, WAYLAND_DISPLAY"
			)
		wayland_socket = os.path.join(xdg_runtime_dir, wayland_display)
		self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM, 0)
		try:
			self._socket.connect(wayland_socket)
		except ConnectionRefusedError:
			self.log("Failed to connect to", wayland_socket)
			self.log()
			raise

		self._leftover = b''
		self._incoming_fds = list()
		self._event_handlers = dict()

		self._read_callbacks = dict()
		self._write_callbacks = dict()
		self._timer_callbacks = dict()

		self.loop = eventloop_integration
		if self.loop is None:
			self.loop = DummyIntegration()
		try:
			self.add_reader(self.fileno(), self.do_read)
		except NotImplementedError:
			pass

		self.display = Display(self)
		self.display.do_sync(self.on_initial_sync)

	def shutdown(self):
		try:
			self.remove_reader(self.fileno())
		except NotImplementedError:
			pass
		self._socket.close()
		raise WaylandDisconnected()

	def on_initial_sync(self, data):
		self.display.registry.on_initial_sync()
		for interface in tuple(self._event_handlers.values()):
			if isinstance(interface, Interface):
				if interface != self.display.registry:
					interface.on_initial_sync()

	def fileno(self):
		return self._socket.fileno()

	# internal loop callbacks
	def _notify_read_cb(self, fd):
		if fd not in self._read_callbacks:
			self.log(f"Ignoring read cb for fd {fd}")
			return
		callback, args, kwargs = self._read_callbacks[fd]
		callback(*args, **kwargs)

	def _notify_timer_cb(self, timer_id):
		if timer_id not in self._timer_callbacks:
			self.log(f"Ignoring timer cb for timer id {timer_id}")
			return
		oneshot, callback, args, kwargs = self._timer_callbacks[timer_id]
		callback(*args, **kwargs)
		if oneshot:
			del self._timer_callbacks[timer_id]

	# public API
	def add_reader(self, fd, callback, *args, **kwargs):
		self.loop.create_reader(fd, self._notify_read_cb)
		self._read_callbacks[fd] = (callback, args, kwargs)

	def add_timer(self, interval_in_s, callback, *args, oneshot=False, **kwargs):
		timer_id = self.loop.create_timer(interval_in_s, self._notify_timer_cb, oneshot=oneshot)
		self._timer_callbacks[timer_id] = (oneshot, callback, args, kwargs)
		return timer_id

	def remove_reader(self, fd):
		if fd not in self._read_callbacks:
			self.log(f"Warning: FD {fd} does not refer to a known fd. Not removing reader.")
			return
		self.loop.remove_reader(fd)
		del self._read_callbacks[fd]

	def remove_timer(self, timer_id):
		if timer_id not in self._timer_callbacks:
			self.log(f"Warning: Timer {timer_id} does not refer to a known timer. Not removing.")
			return
		self.loop.remove_timer(timer_id)
		del self._timer_callbacks[timer_id]

	# internals
	def do_read(self):
		fds = array.array('i')
		try:
			# We allow receiving up to 32 FDs in a single call. If there
			# are more filedescriptors pending they will be automatically
			# closed by the Linux kernel. See man 7 unix (part SCM_RIGHTS).
			# All received FDs which force the open FD count above the
			# process limit are also automatically closed.

			# TODO: we should likely keep on eye on the limit (getrlimit).
			#       + possibly set it to the hard limit while starting.
			data, aux_data, msg_flags, address = self._socket.recvmsg(
				4096, socket.CMSG_SPACE(32 * fds.itemsize)
			)
		except OSError as e:
			if e.errno != errno.EBADF:
				raise
			try:
				self.remove_reader(self.fileno())
			except NotImplementedError:
				pass
			raise WaylandDisconnected()

		for cmsg_level, cmsg_type, cmsg_data in aux_data:
			if (
				cmsg_level == socket.SOL_SOCKET and
				cmsg_type == socket.SCM_RIGHTS
			):
				# Received FDs, append them to _incoming_fds
				# where event handlers may .pop(0) them again.
				fds.frombytes(cmsg_data)
				self._incoming_fds.extend(fds)

		if not data and not aux_data:
			raise WaylandDisconnected()

		fds = self._incoming_fds
		data = self._leftover + data
		while len(data) >= 8:
			obj_id, sizeop = struct.unpack('=II', data[:8])
			size = sizeop >> 16
			op = sizeop & 0xffff
			if len(data) < size:
				break
			argdata = data[8:size]
			data = data[size:]
			self._handle_event(obj_id, op, argdata, fds)
		self._leftover = data

	def _obj_id_generator(self):
		next_id = 2
		while True:
			if self._obj_ids_reuse:
				yield self._obj_ids_reuse.pop(0)
				continue
			yield next_id
			next_id += 1

	def get_new_obj_id(self):
		return next(self._obj_ids)

	def free_obj_id(self, obj_id):
		obj = self._event_handlers.get(obj_id)
		if obj is not None:
			if isinstance(obj, Interface):
				obj.on_destroyed()
			del self._event_handlers[obj_id]
		self._obj_ids_reuse.append(obj_id)

	def get_obj(self, obj_id):
		return self._event_handlers.get(obj_id)

	def sync(self, callback):
		self.display.do_sync(callback)

	def bind(self, interface):
		self.display.registry.do_bind(interface)
		self.add_event_handler(interface)

	def add_event_handler(self, obj_id, callback=None):
		if isinstance(obj_id, Interface):
			callback = obj_id
			obj_id = callback.obj_id
		elif not callable(callback):
			raise RuntimeError(f"Invalid callback supplied to add_event_handler: {callback}.")

		if obj_id is None:
			raise RuntimeError(f"Can't add event handler for {callback}. Object ID is None.")

		if obj_id in self._event_handlers:
			existing = self._event_handlers[obj_id]
			raise RuntimeError(f"Can't add event handler. Event handler already installed for {obj_id}: {existing}.")

		self._event_handlers[obj_id] = callback

	def remove_event_handler(self, obj_id):
		if isinstance(obj_id, Interface):
			obj_id = obj_id.obj_id
		if obj_id not in self._event_handlers:
			raise RuntimeError(f"Can't remove event handler with obj_id {obj_id}: Not actually attached.")
		del self._event_handlers[obj_id]

	def _handle_event(self, obj_id, evt_id, data, fds):
		callback = self._event_handlers.get(obj_id)
		if isinstance(callback, Interface):
			if len(callback._events) <= evt_id:
				self.log(f"No idea how to handle event {callback.name}.{evt_id}({data})")
			else:
				callback._events[evt_id](data, fds)
		elif callable(callback):
			callback(data)
		else:
			raise RuntimeError(f"_handle_event() got invalid callback: {callback} of type {type(callback)}")

	def send_opcode(self, obj_id, opcode, data=b'', fds=None):
		size = 8 + len(data)
		sizeop = size << 16 | opcode
		data = struct.pack('=II', obj_id, sizeop) + data

		# TODO: wrap in try except and raise WaylandDisconnected()
		sent = 0
		if fds is not None:
			if isinstance(fds, int):
				fds = (fds,)
			sent += self._socket.sendmsg(
				[data], [
					(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", fds))
				]
			)
		while sent != len(data):
			if sent:
				self.log(f"Sending additional data chunk. {sent}/{len(data)} sent")
			sent += self._socket.sendmsg([data[sent:]])

	def log(self, *msg):
		name = f"[{repr(self)}]"
		print(f" {name:^25s} ", *msg)

	def __repr__(self):
		return self.__class__.__name__
