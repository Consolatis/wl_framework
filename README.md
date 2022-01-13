### Scope
wl_framwork is a pure Python implementation of the Wayland wire protocol and a (very) small subset of Wayland protocols with a focus on integrating well into existing event loops.
Following event loops are supported:
- poll()
- asyncio
- GLib / Gtk

Adding more event loop integrations (like for Qt) should be trivial.
See [DummyIntegration](wl_framework/loop_integrations/dummy.py). PRs welcome.

### Dependencies
None

### Reliability

This software is in alpha stage. API breakage may occur.

### Executing examples
```
$ python3 -m examples.wl_monitor
$ PYTHONPATH=. examples/wl_monitor.py
$ ./run_example examples/wl_monitor.py
```

### Supported protocols
- [wlr-foreign-toplevel-management-unstable-v1](https://gitlab.freedesktop.org/wlroots/wlr-protocols/-/blob/master/unstable/wlr-foreign-toplevel-management-unstable-v1.xml) (misses output_enter / output_leave)
- [wlr-data-control-unstable-v1.xml](https://gitlab.freedesktop.org/wlroots/wlr-protocols/-/blob/master/unstable/wlr-data-control-unstable-v1.xml) (misses setting own selections)

### Examples
- [wl_monitor](examples/wl_monitor.py) Console monitor for window and clipboard changes. Good starting point for an overview of the API + shows how to use it with asyncio.
- [wlctrl](examples/wlctrl.py) Very basic console control of windows.
- [wl_example_panel](examples/wl_example_panel.py) Very basic but fully functional tasklist panel in 225 SLOC. Requires python-gi + GTK3 and GtkLayerShell typelibs.

### AsyncIO
The whole framework is synchronous, so no `async def` nor `await` are to be seen.  
However, care is taken to not block the eventloop for unreasonable time which is accomplished internally by using callbacks. Sometimes those callbacks are provided by the framework user, for example when the user requests the content of the current clipboard selection. They can thus be wrapped into a Future which gets its result set on the synchronious callback.

The wayland connection itself is kept in a blocking state but only read from in a `readable` notification by the event loop. Writing however is being done without waiting for a `writeable` notification which should be fine on a local Unix socket connection. This may change in the future if deemed necessary. Open an issue if you can think of negative side effects of the current design.

### Projects using wl_framework
- ~~[wl_panel](http://github.com/Consolatis/wl_panel)~~ (not released yet)
