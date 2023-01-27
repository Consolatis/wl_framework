import gi
gi.require_version("GLib", "2.0")
from gi.repository import GLib

class GLibIntegration:
	def __init__(self):
		self._fds = dict()
		self._timer_ids = dict()

		# Not using range() as it requires defining a maximum
		def ids():
			x = 0
			while True:
				yield x
				x += 1
		self._timerid = iter(ids())

	def _get_timerid(self):
		return next(self._timerid)

	def _timer_cb(self, args):
		timer_id, callback, oneshot = args
		callback(timer_id)
		call_again = not oneshot
		return call_again

	def _read_cb(self, fd, flags, callback):
		callback(fd)
		return True

	def create_timer(self, interval_in_s, callback, oneshot=False):
		# We need a timer_id in _timer_cb callback.
		# As GLib doesn't actually send it as argument
		# we have to roll our own id.
		_timer_id = self._get_timerid()
		glib_source_id = GLib.timeout_add(
			int(interval_in_s * 1000),
			self._timer_cb,
			(_timer_id, callback, oneshot),
			priority=GLib.PRIORITY_LOW
		)
		self._timer_ids[_timer_id] = glib_source_id
		return _timer_id

	def remove_timer(self, timer_id):
		glib_source_id = self._timer_ids[timer_id]
		del self._timer_ids[timer_id]
		GLib.source_remove(glib_source_id)

	def create_reader(self, fd, callback):
		glib_source_id = GLib.io_add_watch(
			fd,
			GLib.PRIORITY_DEFAULT,
			GLib.IO_IN | GLib.IO_HUP | GLib.IO_NVAL | GLib.IO_ERR,
			self._read_cb,
			callback
		)
		self._fds[fd] = glib_source_id

	def remove_reader(self, fd):
		glib_source_id = self._fds[fd]
		del self._fds[fd]
		GLib.source_remove(glib_source_id)

	def run(self):
		loop = GLib.MainLoop()
		loop.run()
