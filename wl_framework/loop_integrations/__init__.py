from .dummy import DummyIntegration

def AsyncIOIntegration(*args, **kwargs):
	# Defer importing asyncio
	from .asyncio import AsyncIOIntegration as x
	return x(*args, **kwargs)

def GLibIntegration(*args, **kwargs):
	# Defer importing GLib
	from .glib import GLibIntegration as x
	return x(*args, **kwargs)

def PollIntegration(*args, **kwargs):
	# Defer importing select
	from .poll import PollIntegration as x
	return x(*args, **kwargs)
