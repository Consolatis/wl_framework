# ext: https://gitlab.freedesktop.org/wayland/wayland-protocols/-/blob/main/staging/ext-idle-notify/ext-idle-notify-v1.xml
# kde: https://github.com/KDE/plasma-wayland-protocols/blob/master/src/protocols/idle.xml

from .base import (
	ArgUint32,
	Interface,
	UnsupportedProtocolError
)

def IdleNotifyManager(*args, **kwargs):
	for protocol_name in ('org_kde_kwin_idle', 'ext_idle_notifier_v1'):
		try:
			impl = _IdleNotifyManager(protocol_name, *args, **kwargs)
			print("Using protocol ", protocol_name)
			return impl
		except UnsupportedProtocolError as e:
			print(e)

	raise UnsupportedProtocolError(
		"Neither org_kde_kwin_idle nor " +
		"ext_idle_notifier_v1 supported by compositor"
	)


class _IdleNotifyManager(Interface):
	def __init__(self, interface_name, connection, notifier_class):
		super().__init__(connection)
		self.set_name(interface_name)
		self.set_version(1)
		self.bind()

		if not notifier_class:
			raise RuntimeError(
				"IdleNotifyManager requires a subclass of IdleNotifier"
			)
		self._notifier_class = notifier_class

	# Wayland requests
	def destroy(self):
		# The KDE variant doesn't support destroying the manager
		if self.iface_name == 'ext_idle_notifier_v1':
			self.send_command(0)

	def get_idle_notifier(self, idle_time_in_seconds, seat):
		idle_notifier = self._notifier_class(
			self._connection,
			idle_time_in_seconds,
			supports_simulate=self.iface_name != 'ext_idle_notifier_v1'
		)

		data = ArgUint32.create(idle_notifier.obj_id)
		if self.iface_name == 'ext_idle_notifier_v1':
			data += ArgUint32.create(idle_notifier._idle_time_in_ms)
			data += ArgUint32.create(seat.obj_id)
			self.send_command(1, data)
		else:
			# KDE variant uses a different argument
			# ordering and misses the destroy request
			data += ArgUint32.create(seat.obj_id)
			data += ArgUint32.create(idle_notifier._idle_time_in_ms)
			self.send_command(0, data)
		return idle_notifier

class IdleNotifier(Interface):
	def __init__(self, connection, idle_time_in_s, supports_simulate=False):
		super().__init__(connection)
		self.obj_id = self.get_new_obj_id()
		self._idle_time_in_ms = int(idle_time_in_s * 1000)
		self.supports_simulate = supports_simulate
		self.add_event(self._on_idled)
		self.add_event(self._on_resumed)
		connection.add_event_handler(self)

	# API events
	def on_idle(self):
		pass

	def on_resume(self):
		pass

	# Wayland events
	def _on_idled(self, data, fds):
		self.on_idle()

	def _on_resumed(self, data, fds):
		self.on_resume()

	# Wayland requests
	def destroy(self):
		self.send_command(0)

	def simulate_user_activity(self):
		if not self.supports_simulate:
			raise RuntimeError(
				"Only the KDE variant of the idle notifier " +
				"protocol supports simulating user activity"
			)
		self.send_command(1)
