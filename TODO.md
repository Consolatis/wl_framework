
### Loop integrations
- add_writer()

### Connection
- maybe add send queue
	- send_opcode() then has to os.dup(fds) before adding data / fds to queue

### ForeignTopLevel
- add toplevel.output => fill by output_enter / output_leave events

### Imports
- add protocol classes in `protocols/__init__.py`

### Docs
- generic architecture
- how to add a wayland protocol
