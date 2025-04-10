import atexit
import signal
import sys
import threading
import time
import warnings
from collections.abc import Callable
from pathlib import Path
from signal import signal as bind
from types import FrameType
from typing import Any

from kalib.classes import Singleton
from kalib.descriptors import cache
from kalib.internals import Who
from kalib.loggers import Logging

Logger = Logging.Default
NeedRestart = False


@cache
def get_selfpath():
    return Path(sys.argv[0]).resolve()


def get_mtime():
    return get_selfpath().stat().st_mtime


@cache
def quit_at(*, func=sys.exit, signal=None, errno=137, **kw):
    """Quit the program when the runned file is updated or signal is received."""

    def handler(signum, frame):  # noqa: ARG001
        global NeedRestart  # noqa: PLW0603
        NeedRestart = True
        Logger.warning(f'{signal=} received, mark restart as needed')

    if signal:
        bind(signal, handler)

    initial_stamp = get_mtime()
    def on_change(*, sleep=0.0):

        if NeedRestart and signal:
            Logger.warning(f'{signal=} received, quit..')
            func(errno)
            return False

        elif initial_stamp != (ctime := get_mtime()):
            file = get_selfpath()
            Logger.warning(
                f'{file=} updated {time.time() - ctime:.2f} seconds ago, quit..')
            func(errno)
            return False

        if sleep := (sleep or kw.get('sleep', 0.0)):
            time.sleep(sleep)
        return True
    return on_change


class OnExit(metaclass=Singleton):

    def __init__(self):

        self.callbacks   = []
        self.hooks_chain = []

        self.original_hook  = sys.excepthook
        self.already_called = False

        self.inject_hook()
        self.inject_signal_handler()
        self.inject_threading_hook()

        atexit.register(self.teardown)

    def inject_hook(self) -> None:
        sys.excepthook = self.exceptions_hooks_proxy

    def exceptions_hooks_proxy(
        self,
        exc_type  : type[BaseException],
        exc_value : BaseException,
        traceback : Any,
    ) -> None:

        if sys.excepthook != self.exceptions_hooks_proxy:
            self.hooks_chain.append(sys.excepthook)
            self.inject_hook()

        for hook in (*self.hooks_chain, self.original_hook):
            try:
                hook(exc_type, exc_value, traceback)
            except Exception as e:  # noqa: BLE001
                warnings.warn(f'{Who(hook)}: {e!r}', RuntimeWarning, stacklevel=2)

        self.teardown()

    def inject_signal_handler(self) -> None:
        for sig in signal.SIGINT, signal.SIGTERM, signal.SIGQUIT:
            bind(sig, self.signal_handler)

    def signal_handler(
        self,
        signum : int,  # noqa: ARG002
        frame  : FrameType | None,  # noqa: ARG002
    ) -> None:
        self.teardown()
        sys.exit(1)

    def inject_threading_hook(self) -> None:
        threading.excepthook = self.threading_handler

    def threading_handler(self, args: threading.ExceptHookArgs) -> None:
        if args.exc_type is SystemExit:
            return

        self.exceptions_hooks_proxy(
            args.exc_type,
            args.exc_value,
            args.exc_traceback)

    def restore_original_handlers(self) -> None:
        bind(signal.SIGINT, signal.SIG_DFL)
        bind(signal.SIGTERM, signal.SIG_DFL)
        bind(signal.SIGHUP, signal.SIG_DFL)

        sys.excepthook = self.original_hook
        threading.excepthook = threading.__excepthook__

    #

    def schedule(self, func: Callable) -> None:
        self.callbacks.append(func)

    def add_hook(self, func: Callable) -> None:
        self.hooks_chain.append(func)

    #

    def teardown(self) -> None:
        if self.already_called:
            return

        try:
            for func in self.callbacks:
                try:
                    func()
                except BaseException as e:  # noqa: BLE001
                    warnings.warn(f'{Who(func)}: {e!r}', RuntimeWarning, stacklevel=2)

        finally:
            self.already_called = True
            self.restore_original_handlers()


Exit = OnExit()
