"""Different workload manager interface for cell execution magics.

List of defined class:

- :py:class:`BaseMgr` : Abstract class for functionnal specifications
- :py:class:`BasicMgr` : Simple bash execution (testing purposes). One should use ``%%script bash`` or ``%%bash`` magics instead
- :py:class:`SSHMgr` : Execute cell content through SSH on a distant machine.
- :py:class:`SlurmMgr` : Execute cell content as a Slurm job

    .. inheritance-diagram::
        execute_batch_scheduler.backends

"""
import signal
import time
import errno
import io
import sys
import os
import argparse
from subprocess import (Popen, PIPE, check_output, check_call)
from abc import ABCMeta, abstractmethod
from IPython.utils import py3compat
from IPython.core.magic_arguments import MagicArgumentParser


class BaseMgr(object, metaclass=ABCMeta):
    """Abstract base class for description of workload manager interface.

    Any derived class must implement the init function, how to submit
    a cell, how to monitor job progression and how to get output from
    execution.

    """

    # Main Popen command to submit cell content.
    _wlbin = None

    @abstractmethod
    def __init__(self, args, shell, userns):
        """Initialize the workload manager interface.

        Derived class should instanciate a :py:class:`subprocess.Popen` object to interact with.

        Parameters
        ----------
        args : str
            String containing workload scheduler specific arguments.
        shell : str
            Shell to use whithin the workload scheduler
        userns : dict
            User namespace from cell_magics

        """
        self._waiting_steps = 0
        self._running_steps = 0
        self.shebang = ("#!{0} \n".format(shell)).encode('utf8', 'replace')
        # Cell output
        self.out, self.err = None, None
        self._userns = userns

    @abstractmethod
    def submit(self, content):
        """Submission of the cell content to the workload manager.

        Use a :py:class:`subprocess.Popen` instance to comunicate cell content.

        Parameters
        ----------
        content: str
            IPython cell content.
        """
        pass


    @abstractmethod
    def wait_progress(self):
        """Interact with workload manager to notify job
        progression and states."""
        pass

    @abstractmethod
    def get_output(self):
        """Get the job output and error.

        Returns
        -------
        stdout: str
            Job standard output
        stderr: str
            Job standard errput
        """
        return None, None

    def _interrupt(self):
        """Handle signals to kill :py:class:`subprocess.Popen` instance"""
        try:
            self.p.send_signal(signal.SIGINT)
            time.sleep(0.1)
            if self.p.poll() is not None:
                print("Process is interrupted.")
                return
            self.p.terminate()
            time.sleep(0.1)
            if self.p.poll() is not None:
                print("Process is terminated.")
                return
            self.p.kill()
            print("Process is killed.")
        except OSError:
            pass
        except Exception as e:
            print("Error while terminating subprocess (pid=%i): %s" \
                % (self.p.pid, e))

    def _print_step_and_wait(self, s, silent=False):
        """Print progression.

        Display a :
          - ``.`` every second during 10 seconds
          - ``o`` every 10 seconds during next 100 seconds
          - ``O`` every minutes during next 10 minutes
          - ``@`` every 10 minutes

        Arguments:
        ----------
        - s : number of steps so far
        """
        # Get appropriate step limit (l), time to wait (t) and
        # character to display (c)
        l, t, c = [v for v in ((10, 1, '.'),
                               (20, 10, 'o'),
                               (30, 60, 'O'),
                               (1e12, 600, '@')) if s < v[0]][0]
        if s < l:
            if not silent:
                sys.stdout.write(c)
            time.sleep(t)
        sys.stdout.flush()

    def _step_running(self, silent=False):
        """Performs one more running step."""
        if not silent and self._running_steps == 0:
            sys.stdout.write("Running ")
        self._running_steps += 1
        self._print_step_and_wait(self._running_steps, silent=silent)

    def _step_waiting(self, silent=False):
        """Performs one more waiting step."""
        if not silent and self._waiting_steps == 0:
            sys.stdout.write("Waiting for resources ")
        self._waiting_steps += 1
        self._print_step_and_wait(self._waiting_steps, silent=silent)


class BasicMgr(BaseMgr):
    """Basic  backend.

    Use a simple bash execution for testing purposes.
    This is not a replacement of the builtin IPython ``%%bash`` magics"""

    _wlbin = ['bash', ]

    def __init__(self, args, shell, userns):
        """Initialize the default manager"""
        super(BasicMgr, self).__init__(args, shell, userns)
        self.cmd = self._wlbin + args

        # Build Popen instance
        try:
            self.p = Popen(self.cmd, stdout=PIPE, stderr=PIPE, stdin=PIPE,)
        except OSError as e:
            if e.errno == errno.ENOENT:
                print("Couldn't find program: %r" % self.cmd[0])
                return
            else:
                raise e

    def submit(self, content):
        """Submit the cell content to the Popen instance.
        Return the output and error."""
        # Parse cell content
        script = self.shebang
        script += content.encode('utf8', 'replace')
        if not script.endswith(b'\n'):
            script += b'\n'

        # Submit cell content to Popen instance
        try:
            out, err = self.p.communicate(script)
        except KeyboardInterrupt:
            self._interrupt()
            return
        self.out = py3compat.bytes_to_str(out)
        self.err = py3compat.bytes_to_str(err)
        return(self.out, self.err)

    def wait_progress(self):
        """Skip progression. Cell already executed on submit."""
        pass

    def get_output(self):
        """Skip ouptut. Cell output already displayed on submit"""
        return None, None


class SSHMgr(BaseMgr):
    """SSH based manager.

    Reach a distant machine through SSH to execute cell content as a script.
    SSH is running in batch mode without standard input interaction with
    user, so it must connect without password or passphrase.


    .. todo::
        Add a `user` argument to change from default user connexion.
    """

    _wlbin = ['ssh', '-n']

    def __init__(self, args, shell, userns):
        """Initialize the workload manager interface for SSH.

        It rely on ``ssh -n`` so ssh must connect without any password
        and passphrase. The ssh command is achieved through a :py:class:`subprocess.Popen` object

        Parameters
        ----------
        args : str
            String containing workload scheduler specific arguments.
        shell : str
            Shell to use whithin the workload scheduler
        userns : dict
            User namespace from cell_magics
        """
        super(SSHMgr, self).__init__(args, shell, userns)
        parser = MagicArgumentParser()
        parser.add_argument('--host', type=str, default='localhost',
                            help='Machine to reach (default = localhost)')
        parser.add_argument('--pid', type=str,
                            help='Variable to store SSH process pid')
        _args, cmd = parser.parse_known_args(args)
        self.cmd = self._wlbin + [_args.host, ] + cmd
        # SSH Cannot fork into background without a command to execute.
        # Popen instance is created in submit

    def submit(self, content):
        """Submit the cell content to the Popen instance.

        Parameters
        ----------
        content: str
            IPython cell content.

        """
        self._is_terminated = False

        # Build Popen instance
        try:
            self.p = Popen(self.cmd + [content, ], stdout=PIPE, stderr=PIPE)
        except OSError as e:
            if e.errno == errno.ENOENT:
                print("Couldn't find program: %r" % self.cmd[0])
                return
            else:
                raise e
        except KeyboardInterrupt:
            self._interrupt()
            self._is_terminated = True
        # SSH output is bind to Popen command output
        if self.p.poll() is None:
            if _args.pid:
                self._userns[_args.pid] = self.p.pid
            return ("SSH started with pid: {0}\n".format(self.p.pid), '')
        else:
            self._is_terminated = True
            return self.get_output()

    def wait_progress(self, silent=False):
        """Wait for progression.

        Parameters
        ----------
        slient : bool (default=False)
            Display or not a progression state.
        """
        while self.p.poll() is None:
            self._step_running(silent=silent)
        if not silent:
            sys.stdout.write("\nDone\n")
            sys.stdout.flush()
        self._is_terminated = True

    def get_output(self):
        """Get job output

        Returns
        -------
        stdout: str
            Job standard output
        stderr: str
            Job standard errput
        """
        if self._is_terminated:
            if self.out is None and self.err is None:
                self.out = py3compat.bytes_to_str(b''.join(self.p.stdout.readlines()))
                self.err = py3compat.bytes_to_str(b''.join(self.p.stderr.readlines()))
            return(self.out, self.err)
        else:
            return None


class SlurmMgr(BaseMgr):
    """Slurm workload manager.

    It enforces the slurm standard output and error files to be read and
    display in Cell output after completion.


    Slurm output and error files are stored in ``$HOME/python-execute-slurm.${SLURM_JOB_ID}.[out|err]``.

    .. todo::
        Add a way to change out/err slurm files location.

    """

    _wlbin = ['sbatch', '-n', '1', ]
    _end_states = ('CANCELLED', 'COMPLETED', 'FAILED',
                   'NODE_FAIL', 'PREEMPTED', 'TIMEOUT')
    _wait_states = ('CONFIGURING', 'PENDING')
    _run_states = ('COMPLETING', 'RUNNING', 'SUSPENDED')

    def __init__(self, args, shell, userns):
        """Initialize the slurm submission.

        The ``sbatch`` command is achieved through a :py:class:`subprocess.Popen` object

        Parameters
        ----------
        args : str
            String containing workload scheduler specific arguments.
        shell : str
            Shell to use whithin the workload scheduler
        userns : dict
            User namespace from cell_magics
        """
        super(SlurmMgr, self).__init__(args, shell, userns)

        from . import _DEFAULT_SLURM_OUTERR_FILE
        if _DEFAULT_SLURM_OUTERR_FILE is None:
            self._outerr_files = os.path.join(os.environ['HOME'], "python-execute-slurm.%J")
        else:
            self._outerr_files = _DEFAULT_SLURM_OUTERR_FILE

        parser = MagicArgumentParser()
        parser.add_argument('--jobid', type=str,
                            help='Variable to store Slurm Job Id')
        _args, cmd = parser.parse_known_args(args)
        self.cmd = self._wlbin + cmd + [
            '--output=' + self._outerr_files + '.out',
            '--error=' + self._outerr_files + '.err']
        self._is_started = False
        self._is_terminated = False
        self._args_jobid = _args.jobid

        # Build Popen instance
        try:
            self.p = Popen(self.cmd, stdout=PIPE, stderr=PIPE, stdin=PIPE,)
        except OSError as e:
            if e.errno == errno.ENOENT:
                print("Couldn't find program: %r" % self.cmd[0])
                return
            else:
                raise e

    def submit(self, content):
        """Submission of the cell content to the workload manager.

        Use a Popen instance.
        Return the output and error of submission.

        Parameters
        ----------
        content: str
            IPython cell content.

        Returns
        -------
        stdout: str
            Submission command standard output.
        stderr: str
            Submission command standard errput.

        """
        script = self.shebang
        script += content.encode('utf8', 'replace')
        if not script.endswith(b'\n'):
            script += b'\n'
        try:
            out, err = self.p.communicate(script)
        except KeyboardInterrupt:
            self._interrupt()
            return
        out = py3compat.bytes_to_str(out)
        err = py3compat.bytes_to_str(err)
        # Get the jobid
        self._jobid = 0
        if out.find("Submitted batch job") == 0:
            self._jobid = int(out.split(' ')[-1])
            self._is_started = True
            if self._args_jobid:
                self._userns[self._args_jobid] = self._jobid
        else:
            sys.stderr.write("Error during job submission\n")
            self._is_terminated = True
        return (out, err)

    def _get_job_state(self):
        """Find job state"""
        sacct = "sacct -j{0} --format=State -n -X".format(self._jobid)
        jobstate = check_output(sacct.split(' '))
        if (jobstate == b''):
            squeue = "squeue -j{0} -h -o '%T'".format(self._jobid)
            jobstate = check_output(squeue.split(' '))
        return py3compat.bytes_to_str(jobstate)

    def wait_progress(self, silent=False):
        """Interact with workload manager to notify job
        progression and states

        Parameters
        ----------
        slient : bool (default=False)
            Display or not a progression state.
        """
        if self._is_started:
            jobstate = self._get_job_state()
            try:
                while all([jobstate.find(s) < 0 for s in self._end_states]):
                    if any([jobstate.find(s) >= 0 for s in self._wait_states]):
                        self._step_waiting(silent=silent)
                    if any([jobstate.find(s) >= 0 for s in self._run_states]):
                        if(self._waiting_steps > 0 and self._running_steps == 0):
                            if not silent:
                                sys.stdout.write("\n")
                        self._step_running(silent=silent)
                    jobstate = self._get_job_state()
            except KeyboardInterrupt:
                sys.stdout.write("Terminate job {0} \n".format(self._jobid))
                sys.stdout.flush()
                check_call((['scancel', str(self._jobid)]))
                time.sleep(1)
                jobstate = self._get_job_state()
            self._is_terminated = True

            if not silent:
                if(self._waiting_steps > 0 or self._running_steps > 0):
                    sys.stdout.write("\n")
                sys.stdout.write("End batch job {0} Status: {1}\n".format(
                    self._jobid, jobstate))
                sys.stdout.flush()

    def get_output(self):
        """Get the job output and error.

        Read slurm standard and output files.

        Returns
        -------
        stdout: str
            Job standard output read from slurm output file.
        stderr: str
            Job standard errput read from slurm error file.
        """
        if self._is_started and self._is_terminated:
            if self._get_job_state().find('COMPLETED') < 0:
                sys.stderr.write("Slurm command was : " + " ".join(self.cmd) + "\n")
                sys.stderr.flush()
            job_f = self._outerr_files.replace('%J', str(self._jobid))
            job_out_f = job_f + '.out'
            job_err_f = job_f + '.err'
            job_out = ""
            if self.out is None and self.err is None:
                try:
                    with open(job_out_f, 'r') as f:
                        job_out = f.read()
                except FileNotFoundError:
                    sys.stderr.write("File not found : {0}\n".format(job_out_f))
                    sys.stderr.flush()
                    job_err = ""
                try:
                    with open(job_err_f, 'r') as f:
                        job_err = f.read()
                except FileNotFoundError:
                    sys.stderr.write("File not found : {0}\n".format(job_err_f))
                    sys.stderr.flush()
                self.out, self.err = job_out, job_err
            return(self.out, self.err)
        else:
            return(None, None)
