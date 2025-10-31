"""Wrapper for handling all errors in entry point."""

from functools import wraps
from typing import Any, Callable, Iterable, Optional, Type, TypeVar, overload

T = TypeVar("T", bound=Callable[..., Any])

_iterable_exception = tuple[Type[BaseException]] | list[Type[BaseException]]
_exception = Type[BaseException] | _iterable_exception


class ErrorHandler:
    """Decorator for catching exceptions and printing logs."""

    def __init__(self, exception: Optional[_exception] = None, exit_on_exception: bool = False):
        # Sets default exception (empty tuple) if none was provided
        if exception is None:
            self.exception: _iterable_exception = tuple[Type[BaseException]]()
        # Changes exception class to tuple if it's class
        elif not isinstance(exception, Iterable):
            self.exception = (exception,)
        else:
            self.exception = exception

        # Sets exit_on_exception
        self.exit_on_exception = exit_on_exception

"""Enhanced error handling with user-friendly messages and recovery suggestions."""

from functools import wraps
from typing import Any, Callable, Iterable, Optional, Type, TypeVar, overload

T = TypeVar("T", bound=Callable[..., Any])

_iterable_exception = tuple[Type[BaseException]] | list[Type[BaseException]]
_exception = Type[BaseException] | _iterable_exception


class ErrorHandler:
    """Enhanced decorator for catching exceptions with user-friendly error reporting."""

    def __init__(self, exception: Optional[_exception] = None, exit_on_exception: bool = False):
        # Sets default exception (empty tuple) if none was provided
        if exception is None:
            self.exception: _iterable_exception = tuple[Type[BaseException]]()
        # Changes exception class to tuple if it's class
        elif not isinstance(exception, Iterable):
            self.exception = (exception,)
        else:
            self.exception = exception

        # Sets exit_on_exception
        self.exit_on_exception = exit_on_exception

    def __call__(self, func: T) -> Callable[..., Optional[T]]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Optional[T]:
            try:
                return func(*args, **kwargs)
            except KeyboardInterrupt:
                from mac_cleanup.console import console

                # Print exit message
                console.print("\n[warning]Operation cancelled by user.")

                # Exit if prompted
                if self.exit_on_exception:
                    exit(0)
            # Exclude SystemExit from BaseException clause
            except SystemExit as err:
                raise err
            # Catch all other errors
            except BaseException as err:
                # Clause for not expected error
                if type(err) not in self.exception:
                    self._handle_unexpected_error(err)

        return wrapper

    def _handle_unexpected_error(self, err: BaseException) -> None:
        """Handle unexpected errors with user-friendly messages and recovery suggestions."""
        from mac_cleanup.console import console, print_panel

        error_type = type(err).__name__
        error_message = str(err)

        # Categorize errors and provide user-friendly messages
        if "Permission" in error_type or "permission" in error_message.lower():
            self._handle_permission_error(error_message)
        elif "FileNotFound" in error_type or "No such file" in error_message:
            self._handle_file_not_found_error(error_message)
        elif "Timeout" in error_type or "timeout" in error_message.lower():
            self._handle_timeout_error(error_message)
        elif "Command" in error_type or "command" in error_message.lower():
            self._handle_command_error(error_message)
        elif "Security" in error_type or "security" in error_message.lower():
            self._handle_security_error(error_message)
        else:
            self._handle_generic_error(err, error_type, error_message)

        # Exit if prompted
        if self.exit_on_exception:
            exit(1)

    def _handle_permission_error(self, error_message: str) -> None:
        """Handle permission-related errors."""
        from mac_cleanup.console import print_panel

        print_panel(
            text="[danger]Permission Error[/danger]\n\n"
                 f"[dim]{error_message}[/dim]\n\n"
                 "[info]💡 Suggestions:[/info]\n"
                 "• Run with administrator privileges: [code]sudo mac-cleanup-py[/code]\n"
                 "• Check file permissions: [code]ls -la <path>[/code]\n"
                 "• Some system files cannot be modified for security reasons",
            title="[danger]Access Denied"
        )

    def _handle_file_not_found_error(self, error_message: str) -> None:
        """Handle file not found errors."""
        from mac_cleanup.console import print_panel

        print_panel(
            text="[warning]File or Directory Not Found[/warning]\n\n"
                 f"[dim]{error_message}[/dim]\n\n"
                 "[info]💡 Suggestions:[/info]\n"
                 "• Verify the path exists: [code]ls <path>[/code]\n"
                 "• Check for typos in file/directory names\n"
                 "• Some cleanup targets may have been moved or deleted",
            title="[warning]Path Error"
        )

    def _handle_timeout_error(self, error_message: str) -> None:
        """Handle timeout errors."""
        from mac_cleanup.console import print_panel

        print_panel(
            text="[warning]Operation Timed Out[/warning]\n\n"
                 f"[dim]{error_message}[/dim]\n\n"
                 "[info]💡 Suggestions:[/info]\n"
                 "• The operation took too long and was stopped for safety\n"
                 "• Try running with fewer items or in smaller batches\n"
                 "• Check system performance and available resources",
            title="[warning]Timeout"
        )

    def _handle_command_error(self, error_message: str) -> None:
        """Handle command execution errors."""
        from mac_cleanup.console import print_panel

        print_panel(
            text="[danger]Command Execution Failed[/danger]\n\n"
                 f"[dim]{error_message}[/dim]\n\n"
                 "[info]💡 Suggestions:[/info]\n"
                 "• Verify the command is available on your system\n"
                 "• Check command syntax and arguments\n"
                 "• Some commands may be restricted for security",
            title="[danger]Command Error"
        )

    def _handle_security_error(self, error_message: str) -> None:
        """Handle security-related errors."""
        from mac_cleanup.console import print_panel

        print_panel(
            text="[danger]Security Violation[/danger]\n\n"
                 f"[dim]{error_message}[/dim]\n\n"
                 "[info]💡 Security Features:[/info]\n"
                 "• Dangerous commands are blocked for safety\n"
                 "• System-critical paths are protected\n"
                 "• Large operations require confirmation\n"
                 "• All actions are logged for review",
            title="[danger]Security Error"
        )

    def _handle_generic_error(self, err: BaseException, error_type: str, error_message: str) -> None:
        """Handle generic/unexpected errors."""
        from logging import basicConfig, getLogger
        from rich.logging import RichHandler
        from mac_cleanup.console import console, print_panel

        # Set logger config for detailed error reporting
        basicConfig(
            level="ERROR",
            format="%(message)s",
            datefmt="[%X]",
            handlers=[RichHandler(rich_tracebacks=True)],
        )

        # Get logger
        log = getLogger("EntryPoint")

        # Log detailed error information
        log.exception("Unexpected error occurred")

        # Show user-friendly error panel
        print_panel(
            text="[danger]Unexpected Error[/danger]\n\n"
                 f"[dim]{error_type}: {error_message}[/dim]\n\n"
                 "[info]💡 What to do:[/info]\n"
                 "• Check the detailed error log above\n"
                 "• Report this issue if it persists\n"
                 "• Try running in dry-run mode first: [code]mac-cleanup-py -n[/code]",
            title="[danger]Application Error"
        )


@overload
def catch_exception(
    func: T, exception: Optional[_exception] = ..., exit_on_exception: bool = ...
) -> T: ...  # pragma: no cover (coverage marks line as untested)


@overload
def catch_exception(
    func: None = ..., exception: Optional[_exception] = ..., exit_on_exception: bool = ...
) -> ErrorHandler: ...  # pragma: no cover (coverage marks line as untested)


def catch_exception(
    func: Optional[T] = None, exception: Optional[_exception] = None, exit_on_exception: bool = True
) -> ErrorHandler | Callable[..., Optional[T]]:
    """
    Decorator for catching exceptions and printing logs.

    :param func: Function to be decorated
    :param exception: Expected exception(s)
    :param exit_on_exception: If True, exit after unexpected exception was handled
    :return: Decorated function
    """

    err_handler_instance: ErrorHandler = ErrorHandler(exception=exception, exit_on_exception=exit_on_exception)

    if func:
        err_handler_call: Callable[..., Optional[T]] = err_handler_instance(func)
        return err_handler_call

    return err_handler_instance
