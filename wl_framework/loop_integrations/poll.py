import time
import select

class PollIntegration:
	"""
		If you use this Integration with an existing poll object
		make sure to call handle_event(fd) once you got an event.
		You may use 'fd in pollIntegration' to check if the fd you
		got an event for was registered in this class before calling.
		You should also call check_timers() roughly about every second
		(or more, or less, depending on how exact you want your timers
		to be).
	"""
	def __init__(self, poll_obj=None):
		self._poll = poll_obj
		if not self._poll:
			self._poll = select.poll()
		self._callbacks = dict()
		self._timers = dict()
		# Not using range() as it requires defining a maximum
		def ids():
			x = 0
			while True:
				yield x
				x += 1
		self._timerid = iter(ids())

	def _get_timerid(self):
		return next(self._timerid)

	def create_timer(self, interval_in_s, callback, oneshot=False):
		# Wouldn't it be great if base Python would have a timerfd wrapper?
		timer_id = self._get_timerid()
		run_at = time.monotonic() + interval_in_s
		self._timers[timer_id] = (run_at, oneshot, interval_in_s, callback)
		return timer_id

	def remove_timer(self, timer_id):
		del self._timers[timer_id]

	def __contains__(self, fd):
		return fd in self._callbacks

	def create_reader(self, fd, callback):
		self._poll.register(fd, select.POLLIN | select.POLLERR | select.POLLHUP)
		self._callbacks[fd] = callback

	def remove_reader(self, fd):
		self._poll.unregister(fd)
		del self._callbacks[fd]

	def handle_event(self, fd):
		callback = self._callbacks[fd]
		callback(fd)

	def check_timers(self):
		# Wouldn't it be great if base Python would have a timerfd wrapper?
		now = time.monotonic()
		for timer_id in tuple(self._timers):
			if timer_id not in self._timers:
				# Deleted in the meantime, probably by us
				continue
			run_at, oneshot, interval, callback = self._timers[timer_id]
			if now < run_at:
				continue
			callback(timer_id)

			if oneshot:
				del self._timers[timer_id]
			else:
				run_at = now + interval
				self._timers[timer_id] = (run_at, oneshot, interval, callback)

	def run(self):
		while True:
			for fd, evt in self._poll.poll(1000):
				self.handle_event(fd)
			self.check_timers()
