class DummyIntegration:

	def create_timer(self, interval_in_s, callback, oneshot=False):
		# Returns opaque timer_id
		raise NotImplementedError()

	def remove_timer(self, timer_id):
		raise NotImplementedError()

	def create_reader(self, fd, callback):
		raise NotImplementedError()

	def remove_reader(self, fd):
		raise NotImplementedError()
