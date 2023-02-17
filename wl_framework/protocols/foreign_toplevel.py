# https://gitlab.freedesktop.org/wlroots/wlr-protocols/-/blob/master/unstable/wlr-foreign-toplevel-management-unstable-v1.xml

from .base import (
	ArgUint32,
	ArgString,
	Interface
)

class ForeignTopLevel(Interface):

	def __init__(self, connection):
		super().__init__(connection)
		self.set_name('zwlr_foreign_toplevel_manager_v1')
		self.set_version(3)
		self.add_event(self.on_new_toplevel)
		self.add_event(self.on_finished)
		self.windows = dict()
		self.bind()

	# Wayland events
	def on_new_toplevel(self, data, fds):
		_, obj_id = ArgUint32.parse(data)
		toplevel = TopLevel(self._connection, obj_id=obj_id, parent=self)
		self.windows[obj_id] = toplevel
		self.on_toplevel_created(toplevel)

	def on_finished(self, data, fds):
		pass

	# Wayland requests
	def stop(self):
		self.send_command(0)

	# Custom events
	def on_toplevel_created(self, toplevel):
		pass

	def on_toplevel_synced(self, toplevel):
		pass

	def on_toplevel_closed(self, toplevel):
		pass

	def on_toplevel_output_change(self, toplevel):
		pass

	# Internal handlers
	def _on_toplevel_closed(self, toplevel):
		del self.windows[toplevel.obj_id]
		self.on_toplevel_closed(toplevel)


class TopLevel(Interface):
	STATES = (
		'maximized',
		'minimized',
		'activated',
		'fullscreen'
	)

	def __init__(self, connection, obj_id, parent):
		super().__init__(connection, obj_id=obj_id)
		self.set_name('zwlr_foreign_toplevel_handle_v1')
		self.set_version(parent.version)
		self._events = (
			self.on_title,
			self.on_app_id,
			self.on_output_enter,
			self.on_output_leave,
			self.on_state,
			self.on_done,
			self.on_closed,
			self.on_parent
		)
		connection.add_event_handler(self)
		self._parent = parent
		self.title = ''
		self.app_id = ''
		self.states = tuple()
		self.parent = 0
		self.outputs = set()

	# Wayland events
	def on_title(self, data, fds):
		_, data = ArgString.parse(data)
		self.title = data

	def on_app_id(self, data, fds):
		_, data = ArgString.parse(data)
		self.app_id = data

	def on_output_enter(self, data, fds):
		_, output_id = ArgUint32.parse(data)
		output = self._connection.display.get_output_by_id(output_id)
		self.outputs.add(output)
		self._parent.on_toplevel_output_change(self)

	def on_output_leave(self, data, fds):
		_, output_id = ArgUint32.parse(data)
		output = self._connection.display.get_output_by_id(output_id)
		self.outputs.remove(output)
		self._parent.on_toplevel_output_change(self)

	def on_state(self, data, fds):
		consumed, state_count = ArgUint32.parse(data)
		states = data[consumed:]
		self.states = tuple(self._get_states(states))

	def on_done(self, data, fds):
		self._parent.on_toplevel_synced(self)

	def on_closed(self, data, fds):
		self.destroy()
		self._parent._on_toplevel_closed(self)

	def on_parent(self, data, fds):
		_, data = ArgUint32.parse(data)
		self.parent = data

	# Wayland requests
	def set_maximize(self, enabled=True):
		if enabled:
			self.send_command(0)
		else:
			self.send_command(1)

	def set_minimize(self, enabled=True):
		if enabled:
			self.send_command(2)
		else:
			self.send_command(3)

	def activate(self, seat):
		seat = ArgUint32.create(seat.obj_id)
		self.send_command(4, seat)

	def close(self):
		self.send_command(5)

	# request 6 == set_rectangle

	def destroy(self):
		self._connection.remove_event_handler(self)
		self.send_command(7)

	def set_fullscreen(self, enabled=True):
		if self.version < 2:
			return

		if enabled:
			# TODO: add output argument so we can move
			#       fullscreen'd toplevels between outputs
			data = ArgUint32.create(0)
			self.send_command(8, data)
		else:
			self.send_command(9)

	# Internal parsers
	def _get_states(self, states):
		while len(states):
			consumed, state = ArgUint32.parse(states)
			states = states[consumed:]
			try:
				state = TopLevel.STATES[state]
			except IndexError:
				pass
			yield state
