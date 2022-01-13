# https://gitlab.freedesktop.org/wlroots/wlr-protocols/-/blob/master/unstable/wlr-data-control-unstable-v1.xml

import os
import errno

from .base import (
	ArgUint32,
	ArgString,
	Interface
)

class DataControl(Interface):

	def __init__(self, connection):
		super().__init__(connection)
		self.set_name('zwlr_data_control_manager_v1')
		self.set_version(2)
		self.bind()
		self._sources = dict()
		self._device = self.get_data_device(self._connection.display.seat)

	# Wayland methods
	def create_data_source(self):
		source = DataControlSource(self._connection, self)
		self._sources[source.obj_id] = source
		data = ArgUint32.create(source.obj_id)
		self.send_command(0, data)
		return source

	def get_data_device(self, seat):
		device = DataControlDevice(self._connection, self)
		data = ArgUint32.create(device.obj_id)
		data += ArgUint32.create(seat.obj_id)
		self.send_command(1, data)
		return device

	def destroy(self):
		self.send_command(2)

	# Custom device callbacks
	def on_source_removed(self, source):
		self.log(f"Source {source} has been cancelled")
		del self._sources[source.obj_id]

	def on_new_selection(self, offer):
		self.log(f"New selection: {offer}")

	def on_new_primary_selection(self, offer):
		self.log(f"New primary selection: {offer}")


class DataControlDevice(Interface):

	def __init__(self, connection, parent):
		super().__init__(connection)
		self.obj_id = self.get_new_obj_id()
		self.set_name('zwlr_data_control_device_v1')
		self.set_version(2)
		self.add_event(self.on_data_offer)
		self.add_event(self.on_selection)
		self.add_event(self.on_finished)
		self.add_event(self.on_primary_selection)
		connection.add_event_handler(self)
		self._parent = parent

		self._selection = None
		self._primary_selection = None
		self._offers = dict()

	# Wayland events
	def on_data_offer(self, data, fds):
		_, obj_id = ArgUint32.parse(data)
		offer = DataControlOffer(self._connection, obj_id, self)
		self._offers[obj_id] = offer

	def on_selection(self, data, fds):
		self._set_selection(data, primary=False)

	def on_finished(self, data, fds):
		self.log("Device finished")
		for offer in self._offers.values():
			self.log("  found active offer:", offer)
			offer.destroy()
		self._offers.clear()
		self.destroy()

	def on_primary_selection(self, data, fds):
		self._set_selection(data, primary=True)

	# Wayland methods
	def set_selection(self, source):
		obj_id = 0 if source is None else source.obj_id
		data = ArgUint32.create(obj_id)
		self.send_command(0, data)

	def destroy(self):
		self.send_command(1)
		self._connection.remove_event_handler(self)

	def set_primary_selection(self, source):
		if self.version < 2:
			return
		obj_id = 0 if source is None else source.obj_id
		data = ArgUint32.create(obj_id)
		self.send_command(2, data)

	# Custom callbacks
	#def on_offer_mime(self, offer, mime_type):
	#	#self.log("Got offer for mime_type", mime_type)

	# Custom helpers
	def _set_selection(self, data, primary=False):
		selection_key = f'{"_primary" if primary else ""}_selection'
		_, obj_id = ArgUint32.parse(data)
		if obj_id == 0:
			offer = None
		else:
			offer = self._offers.get(obj_id)
			if offer is None:
				raise RuntimeError(f"Invalid offer for obj_id {obj_id} referenced in on{selection_key} callback")
		old_offer = getattr(self, selection_key)
		if old_offer:
			del self._offers[old_offer.obj_id]
			old_offer.destroy()
		setattr(self, selection_key, offer)
		func = getattr(self._parent, f"on_new{selection_key}")
		func(offer)

class DataControlSource(Interface):

	def __init__(self, connection, parent):
		super().__init__(connection)
		self.obj_id = self.get_new_obj_id()
		self.set_name('zwlr_data_control_source_v1')
		self.set_version(1)
		self.add_event(self.on_send)
		self.add_event(self.on_cancelled)
		connection.add_event_handler(self)
		self._parent = parent

	# Wayland events
	def on_send(self, data, fds):
		# TODO: attach send_fd to IO loop + add write callback
		_, mime_type = ArgString.parse(data)
		send_fd = fds.pop(0)
		self.log(f"Should send data for fd {fd} with mimetype {mime_type}")
		os.close(send_fd)

	def on_cancelled(self, data, fds):
		self._parent.on_source_removed(self)
		self.destroy()

	# Wayland methods
	def offer(self, mime_type):
		self.send_command(0, ArgString.create(mime_type))

	def destroy(self):
		self.send_command(1)
		self._connection.remove_event_handler(self)

class DataControlOffer(Interface):

	def __init__(self, connection, obj_id, parent):
		super().__init__(connection, obj_id=obj_id)
		self.set_name('zwlr_data_control_offer_v1')
		self.set_version(1)
		self.add_event(self.on_offer)
		connection.add_event_handler(self)

		self._parent = parent
		self._mime_types = dict()
		self._transfers = dict()
		self._fd_timers = dict()
		self._timeout = 5

	# Wayland events
	def on_offer(self, data, fds):
		_, mime_type = ArgString.parse(data)
		self._mime_types[mime_type] = None
		#self._parent.on_offer_mime(self, mime_type)

	# Wayland methods
	def receive(self, mime_type, done_callback):
		if mime_type not in self._mime_types:
			raise KeyError(f"{mime_type} not part of offer")
		pipe_read, pipe_write = os.pipe()
		self.log(f"Requesting {mime_type} with read fd {pipe_read} and write_fd {pipe_write}")

		# Send write end of pipe to remote peer and close it on our end
		data = ArgString.create(mime_type)
		self.send_command(0, data, (pipe_write,))
		os.close(pipe_write)

		# Wait for data to receive + create fallback timer to cancel for misbehaving peers
		self._connection.add_reader(pipe_read, self._read_cb, pipe_read, mime_type, done_callback)
		self._idle_timer_add(pipe_read, mime_type)
		self._transfers[mime_type] = b''

	def destroy(self):
		self._connection.remove_event_handler(self)
		self.send_command(1)

	# Custom methods
	def get_mime_types(self):
		return tuple(self._mime_types.keys())

	# Internal helpers
	def _idle_timer_add(self, fd, mime_type):
		if fd in self._fd_timers:
			self.log(f"_idle_timer_add: timer for fd {fd} already active")
			return
		timer_id = self._connection.add_timer(self._timeout,
			self._read_idle, fd, mime_type, oneshot=True
		)
		self._fd_timers[fd] = timer_id

	def _idle_timer_remove(self, fd):
		if fd in self._fd_timers:
			timer_id = self._fd_timers[fd]
			self._connection.remove_timer(timer_id)
			del self._fd_timers[fd]

	# Internal callbacks
	def _read_cb(self, fd, mime_type, done_callback):
		try:
			data = os.read(fd, 1024 * 1024)
		except OSError as e:
			data = None
			if e.errno != errno.EBADF:
				raise
		self._idle_timer_remove(fd)
		if data:
			self._transfers[mime_type] += data
			#self.log("Got data: {:.2f} KiB / {:.2f} KiB".format(
			#	len(data) / 1024, len(self._transfers[mime_type]) / 1024
			#))
			self._idle_timer_add(fd, mime_type)
			return

		self._mime_types[mime_type] = self._transfers[mime_type]
		del self._transfers[mime_type]
		self._connection.remove_reader(fd)
		try:
			os.close(fd)
		except OSError as e:
			if e.errno != errno.EBADF:
				raise
		done_callback(mime_type, self._mime_types[mime_type])

	def _read_idle(self, fd, mime_type):
		if fd not in self._fd_timers:
			self.log(f"Late fd idle notification for for {fd}")
			return
		del self._fd_timers[fd]
		self.log(
			f"Pipe for {mime_type} with fd {fd} idle for {self._timeout} seconds. " +
			"Remote peer likes to block everybody else for no reason. Closing."
		)
		self._transfers[mime_type] = None
		#self._transfers[mime_type] = b'BROKEN_APPLICATION'

		# Let _read_cb deal with cleanup
		os.close(fd)
		self._read_cb(fd, mime_type)
