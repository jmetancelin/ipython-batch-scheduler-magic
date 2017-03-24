"""Cell execution magics definition.

"""
from __future__ import print_function
import sys
from IPython.core.magic import (Magics, magics_class, cell_magic)
from IPython.core import magic_arguments
from IPython.utils.process import arg_split
from IPython.lib.backgroundjobs import BackgroundJobManager

# Import all known backends
from .backends import (BasicMgr, SSHMgr, SlurmMgr)
from . import _DEFAULT_MGR

# The class MUST call this class decorator at creation time
@magics_class
class ExecuteMagics(Magics):
    """Magics for cell execution through workload manager

    List of available workload managers:

    * :class:`execute_batch_scheduler.backends.BasicMgr`

    * :class:`execute_batch_scheduler.backends.SSHMgr`

    * :class:`execute_batch_scheduler.backends.SlurmMgr`

    """

    # Available workload managers
    _wlmgr = {'': BasicMgr, 'ssh': SSHMgr, 'slurm': SlurmMgr}

    @magic_arguments.magic_arguments()
    @magic_arguments.argument(
        '--wlm', type=str, default=_DEFAULT_MGR,
        help="""Workload manager.""")
    @magic_arguments.argument(
        '--shell', type=str, default='/bin/bash',
        help="""Shell to use.""")
    @magic_arguments.argument(
        '--amgr', type=str,
        help="""The variable in which to store workload manager instance.
        If the script is backgrounded, this will be used to get cell output/error
        using `get_output()` method.""")
    @magic_arguments.argument(
        '--bg', action="store_true",
        help="""Whether to run the script in the background.
        If given, the only way to see the output of the command is
        with  `--amgr`.""")
    @cell_magic
    def execute(self, line, cell):
        """Execute given cell content through configured workload scheduler.

        Keep some arguments : ``--wlm``, ``--shell``, ``--bg`` and ``--amgr``.
        Other arguments are passed to workload manager backend.

        Get some extra command line arguments from variable that
        may be overrided in IPython profile configuration file.
        """
        from . import _DEFAULT_LINE_CMD_ARGS
        args, cmd = self.execute.parser.parse_known_args(arg_split(line))

        extra_cmd = []
        if args.wlm == _DEFAULT_MGR:
            if isinstance(_DEFAULT_LINE_CMD_ARGS, dict):
                if args.wlm in _DEFAULT_LINE_CMD_ARGS.keys():
                    extra_cmd = arg_split(
                        _DEFAULT_LINE_CMD_ARGS[args.wlm])
            else:
                extra_cmd = arg_split(_DEFAULT_LINE_CMD_ARGS)
        # Build workload manager instance
        job_mgr = self._wlmgr[args.wlm](
            cmd + extra_cmd, args.shell)
        # Submit the cell as job script
        sub_out, sub_err = job_mgr.submit(cell)
        sys.stdout.write(sub_out)
        sys.stdout.flush()
        sys.stderr.write(sub_err)
        sys.stderr.flush()

        if args.bg:
            self.job_manager = BackgroundJobManager()
            if args.amgr:
                self.shell.user_ns[args.amgr] = job_mgr
            else:
                sys.stderr.write("""Warning: --bg argument specified without
 --amgr (only way to get cell output)\n""")
                sys.stderr.flush()
            self.job_manager.new(job_mgr.wait_progress, kw=dict(silent=True))
            return
        else:
            try:
                job_mgr.wait_progress()
            except KeyboardInterrupt:
                job_mgr.interrupt()

        # Get job output
        job_out, job_err = job_mgr.get_output()
        if job_out:
            sys.stdout.write(job_out)
            sys.stdout.flush()
        if job_err:
            sys.stderr.write(job_err)
            sys.stderr.flush()



def load_ipython_extension(ipython):
    """Load extension.

    Registers the ExecuteMagics
    """
    # The `ipython` argument is the currently active `InteractiveShell`
    # instance, which can be used in any way. This allows you to register
    # new magics or aliases, for example.
    ipython.register_magics(ExecuteMagics)


# def unload_ipython_extension(ipython):
#     """Unload extension

#     Actually doing noting
#     """
#     # If you want your extension to be unloadable, put that logic here.
#     pass
