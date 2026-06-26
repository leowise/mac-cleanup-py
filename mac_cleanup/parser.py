"""Console argument parser configuration."""

from argparse import ArgumentParser, RawTextHelpFormatter
from typing import Optional, final

import attr

from mac_cleanup.__version__ import __version__


@final
@attr.s(slots=True)
class Args:
    dry_run: bool = attr.ib(default=False)
    update: bool = attr.ib(default=False)
    configure: bool = attr.ib(default=False)
    custom_path: bool = attr.ib(default=False)
    force: bool = attr.ib(default=False)
    verbose: bool = attr.ib(default=False)
    safe_delete: bool = attr.ib(default=False)
    restore: bool = attr.ib(default=False)
    command: Optional[str] = attr.ib(default=None)


parser = ArgumentParser(
    description=f"""\
    Python cleanup script for macOS
    Version: {__version__}
    https://github.com/mac-cleanup/mac-cleanup-py\
    """,
    formatter_class=RawTextHelpFormatter,
)

parser.epilog = """\
Examples:
  mac-cleanup cleanup --help
  mac-cleanup dry-run --help
  mac-cleanup restore --help
  mac-cleanup configure --help
  mac-cleanup custom-path --help
"""


def _add_common_flags(target_parser: ArgumentParser) -> None:
    target_parser.add_argument("-n", "--dry-run", help="Run without deleting stuff", action="store_true")
    target_parser.add_argument("-u", "--update", help="Update Homebrew on cleanup", action="store_true")
    target_parser.add_argument("-f", "--force", help="Accept all warnings", action="store_true")
    target_parser.add_argument("-v", "--verbose", help="Print folders to be deleted", action="store_true")
    target_parser.add_argument(
        "-s", "--safe-delete", help="Move files to trash instead of permanent deletion", action="store_true"
    )


subparsers = parser.add_subparsers(
    dest="command",
    title="commands",
    metavar="<command>",
)

cleanup_parser = subparsers.add_parser(
    "cleanup",
    help="Run cleanup",
    description="Run cleanup across configured modules.",
    formatter_class=RawTextHelpFormatter,
)
_add_common_flags(cleanup_parser)

dry_run_parser = subparsers.add_parser(
    "dry-run",
    help="Analyze cleanup without deleting",
    description="Analyze what would be removed and show an estimate.",
    formatter_class=RawTextHelpFormatter,
)
dry_run_parser.add_argument("-v", "--verbose", help="Print folders to be deleted", action="store_true")
dry_run_parser.add_argument("-f", "--force", help="Accept all warnings", action="store_true")
dry_run_parser.set_defaults(dry_run=True)

restore_parser = subparsers.add_parser(
    "restore",
    help="Restore from backups",
    description="Interactively restore files from backups.",
    formatter_class=RawTextHelpFormatter,
)
restore_parser.set_defaults(restore=True)

configure_parser = subparsers.add_parser(
    "configure",
    help="Open configuration",
    description="Open the module configuration screen.",
    formatter_class=RawTextHelpFormatter,
)
configure_parser.set_defaults(configure=True)

custom_path_parser = subparsers.add_parser(
    "custom-path",
    help="Set custom modules path",
    description="Set the path where custom cleanup modules are loaded from.",
    formatter_class=RawTextHelpFormatter,
)
custom_path_parser.set_defaults(custom_path=True)

update_parser = subparsers.add_parser(
    "update",
    help="Update Homebrew during cleanup",
    description="Run cleanup with Homebrew update enabled.",
    formatter_class=RawTextHelpFormatter,
)
_add_common_flags(update_parser)
update_parser.set_defaults(update=True)

subparsers.add_parser(
    "ui",
    help="Launch interactive TUI",
    description="Launch the interactive terminal UI.",
    formatter_class=RawTextHelpFormatter,
)

parser.add_argument("-n", "--dry-run", help="Run without deleting stuff", action="store_true")
parser.add_argument("-u", "--update", help="Update Homebrew on cleanup", action="store_true")
parser.add_argument("-c", "--configure", help="Open module configuration screen", action="store_true")
parser.add_argument("-p", "--custom-path", help="Specify path for custom modules", action="store_true")
parser.add_argument("-f", "--force", help="Accept all warnings", action="store_true")
parser.add_argument("-v", "--verbose", help="Print folders to be deleted", action="store_true")
parser.add_argument(
    "-s", "--safe-delete", help="Move files to trash instead of permanent deletion", action="store_true"
)
parser.add_argument(
    "-r", "--restore", help="Restore files from backups", action="store_true"
)

args = Args()

# Only swallow exit code 2 (argparse parse errors from pytest passing test paths
# as positional args). Code 0 exits (--help, --version) must propagate normally.
try:
    parser.parse_known_args(namespace=args)
except SystemExit as e:
    if e.code != 2:
        raise

# args.dry_run = True  # debug
# args.configure = True  # debug
# args.custom_path = True  # debug
# args.force = True  # debug
# args.verbose = True # debug
