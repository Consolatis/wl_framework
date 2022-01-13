
### Loop integrations
- add_writer()

### Connection
- maybe add send queue
	- send_opcode() then has to os.dup(fds) before adding data / fds to queue

### Imports
- add protocol classes in `protocols/__init__.py`

### Docs
- generic architecture
- how to add a wayland protocol
