#https://raw.githubusercontent.com/pop-os/cosmic-protocols/9c41b6b0ece1672c335e59bf670f8671ce66ed33/unstable/cosmic-workspace-unstable-v1.xml

from .base import (
	ArgString,
	ArgUint32,
	ArgArray,
	Interface,
	UnsupportedProtocolError
)

class CosmicWorkspaceManager(Interface):

	def __init__(self, connection):
		super().__init__(connection)
		self.set_name('zcosmic_workspace_manager_v1')
		self.set_version(1)
		self._events = (
			self._on_workspace_group,
			self._on_done,
			self._on_finished
		)
		self.bind()
		self.groups = list()
		self._new_groups = list()

	# Wayland events
	def _on_workspace_group(self, data, fds):
		_, obj_id = ArgUint32.parse(data)
		self.log(f"new workspace group; {obj_id}")
		group = CosmicWorkspaceGroup(self._connection, obj_id=obj_id, parent=self)
		self.groups.append(group)
		self.on_group(group)

	def _on_done(self, data, fds):
		self.on_sync()

	def _on_finished(self, data, fds):
		self.on_finished()

	# Wayland requests
	def commit(self):
		self.send_command(0)

	def stop(self):
		self.send_command(1)

	# Custom events
	def on_sync(self):
		pass

	def on_group(self, group):
		pass

	def on_workspace(self, workspace):
		pass

	def on_workspace_removed(self, workspace):
		pass

	def on_finished(self):
		pass

class CosmicWorkspaceGroup(Interface):

	CAPS = (
		None,
		'create_workspace',
	)

	def __init__(self, connection, obj_id, parent):
		super().__init__(connection, obj_id=obj_id)
		self._parent = parent
		self.set_name('zcosmic_workspace_group_handle_v1')
		self.set_version(parent.version)
		self._events = (
			self.on_capabilities,
			self.on_output_enter,
			self.on_output_leave,
			self.on_workspace,
			self.on_remove
		)
		connection.add_event_handler(self)

		self.outputs = set()
		self.workspaces = set()
		self.capabilities = tuple()

	# Wayland events
	def on_capabilities(self, data, fds):
		_, data = ArgArray.parse(data)
		self.capabilities = tuple(self._parse_capabilities(data))
		#self.log(f"group capabilities: {', '.join(self.capabilities)}")

	def on_output_enter(self, data, fds):
		_, output_id = ArgUint32.parse(data)
		output = self._connection.display.get_output_by_id(output_id)
		self.outputs.add(output)
		#self.log(f"output enter for {output.name}")

	def on_output_leave(self, data, fds):
		_, output_id = ArgUint32.parse(data)
		output = self._connection.display.get_output_by_id(output_id)
		self.outputs.remove(output)
		#self.log(f"output leave for {output.name}")

	def on_workspace(self, data, fds):
		_, obj_id = ArgUint32.parse(data)
		workspace = CosmicWorkspaceHandle(self._connection, obj_id=obj_id, parent=self)
		self.workspaces.add(workspace)
		self._parent.on_workspace(workspace)

	def on_remove(self, data, fds):
		#self.log("group removed")
		pass

	# Wayland requests
	def create_workspace(self, workspace_name):
		# FIXME: check against capabilities
		arg = ArgString.create(workspace_name)
		self.send_command(0, arg)
		#self.log(f"should create new workspace: {workspace_name}")

	def destroy(self):
		#self.log("Destroying")
		self.send_command(1)

	# Internal helpers
	def _parse_capabilities(self, capabilities):
		while len(capabilities):
			consumed, cap = ArgUint32.parse(capabilities)
			capabilities = capabilities[consumed:]
			try:
				cap = self.CAPS[cap]
				yield cap
			except IndexError:
				self.log(f"Got invalid capability: {cap}")

	# _internal_handlers
	def _on_workspace_removed(self, workspace):
		self.workspaces.remove(workspace)
		self._parent.on_workspace_removed(workspace)

	def __str__(self):
		return f"Group-{self.obj_id}"

class CosmicWorkspaceHandle(Interface):

	CAPS = (
		None,
		'activate',
		'deactivate',
		'remove',
	)

	STATES = (
		'active',
		'urgent',
		'hidden'
	)

	def __init__(self, connection, obj_id, parent):
		super().__init__(connection, obj_id=obj_id)
		self._parent = parent
		self.set_name('zcosmic_workspace_handle_v1')
		self.set_version(parent.version)
		self._events = (
			self.on_name,
			self.on_coordinates,
			self.on_state,
			self.on_capabilities,
			self.on_remove,
		)
		connection.add_event_handler(self)
		self.name = None
		self.states = tuple()
		self.capabilities = tuple()

	# Wayland events
	def on_name(self, data, fds):
		_, name = ArgString.parse(data)
		#self.log(f"workspace name: {name}")
		self.name = name

	def on_coordinates(self, data, fds):
		# FIXME: some array
		#self.log(f"workspace coordinates")
		pass

	def on_state(self, data, fds):
		_, data = ArgArray.parse(data)
		self.states = tuple(self._parse_array(self.STATES, data))
		#self.log("workspace state: " + ', '.join(self.states))

	def on_capabilities(self, data, fs):
		_, data = ArgArray.parse(data)
		self.capabilities = tuple(self._parse_array(self.CAPS, data))
		#self.log("workspace capabilities: " + ', '.join(self.capabilities))

	def on_remove(self, data, fds):
		#self.log("workspace removed")
		self._parent._on_workspace_removed(self)
		self.destroy()

	# Wayland requests
	def destroy(self):
		#self.log("Destroying")
		self._connection.remove_event_handler(self)
		self.send_command(0)

	def activate(self):
		# FIXME: check against capabilities
		self.send_command(1)
		#self.log("activating workspace")

	def deactivate(self):
		# FIXME: check against capabilities
		self.send_command(2)
		#self.log("deactivating workspace")

	def remove(self):
		# FIXME: check against capabilities
		self.send_command(3)
		#self.log("removing workspace")

	# Internal helpers
	def _parse_array(self, states, array):
		while array:
			consumed, val = ArgUint32.parse(array)
			array = array[consumed:]
			try:
				val = states[val]
				yield val
			except IndexError:
				self.log(f"Got invalid {'capability' if states == self.CAPS  else 'state'}: {val}")

	def log(self, *msg):
		if self.name is None:
			name = f"Workspace-{self.obj_id}"
		else:
			name = self.name
		name = f"[{name}]"
		print(f" {name:^25s} ", *msg)

	def on_destroyed(self):
		self.log("We got destroyed. oh noes")
