import asyncio

class AsyncIOIntegration:
	def __init__(self):
		self.loop = asyncio.get_running_loop()
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

	def _timer_cb(self, timer_id, callback, oneshot, _interval):
		now = self.loop.time()
		callback(timer_id)
		if not oneshot:
			self.create_timer(
				_interval, callback,
				oneshot=oneshot,
				_timer_id=timer_id, _start_at=now
			)
		else:
			del self._timer_ids[timer_id]

	def create_timer(self,
		interval_in_s, callback, oneshot=False,
		_timer_id=None, _start_at=None
	):
		# We need a timer_id in _timer_cb() callback.
		# As AsyncIO doesn't actually send it as argument
		# we have to roll our own id.
		if _timer_id is None:
			_timer_id = self._get_timerid()
		if _start_at is None:
			_start_at = self.loop.time()
		timer_obj = self.loop.call_at(
			_start_at + interval_in_s,
			self._timer_cb,
			_timer_id, callback, oneshot, interval_in_s
		)
		self._timer_ids[_timer_id] = timer_obj
		return _timer_id

	def remove_timer(self, timer_id):
		obj = self._timer_ids[timer_id]
		del self._timer_ids[timer_id]
		obj.cancel()

	def create_reader(self, fd, callback):
		self.loop.add_reader(fd, callback, fd)

	def remove_reader(self, fd):
		self.loop.remove_reader(fd)

