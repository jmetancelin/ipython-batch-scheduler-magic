Readme
======

[Complete documentation](https://jmetancelin.github.io/ipython-batch-scheduler-magic/)


Overview
--------

This package provides a IPython [magic commands](http://ipython.readthedocs.io/en/stable/interactive/magics.html) to delegate cell content execution to a workload scheduler.

Workload scheduler are mostly used in High Performance Computing environment to manage resources usability to users. Currently, this package supports only [Slurm](http://slurm). It exists other schedulers, that contributors should feel free to add support:

- [Slurm](http://slurm) (supported)
- OAR
- PBS
- ...

This package is also supporting basic SSH instead of workload scheduler.

This package exposes functionalities through a cell magic command : `%%execute`. Backend is provided in the `execute_batch_scheduler` Python sub-package.


Installation
------------

This package installs through Python distutils :

    python setup.py install

The default backend workload scheduler may be configured on install. Example for slurm:

    python setup.py install --workloadmanager=slurm

Default command line arguments may also be configured on install. Example for setting a specific slurm QOS:

    python setup.py install --workloadmanager=slurm --workloadmanagercmdargs=--quos=ipythoncell

Example for setting a specific slurm QOS and a host for ssh:

    python setup.py install --workloadmanagercmdargs='{"slurm": "--quos=ipythoncell", "ssh": "--host=amachine"}'


The magic command is then activated as an IPython extension:

    In [1]: %load_ext execute_batch_scheduler.execute_magic

Usage example
-------------

A single entry point is the `%%execute` magic:

```text
In [2]: %%execute -n8 -N4
srun -n 8 hostname
...:
Submitted batch job 957969
Running .
End batch job 957969 Status:  COMPLETED

romeo137
romeo137
romeo138
romeo138
romeo139
romeo139
romeo140
romeo140
```

Command line arguments (`-n8 -N4` in the example above) are passed to the workload manager submission command, `salloc` here for Slurm. Some command line arguments are reserved, and intercepted, by the magic command. See below

#### Common arguments:

- `--wlm=<backend>` : select the backend workload manager (currently available: `ssh`, `slurm`). Default value is set at install.
- `--shell=<SHELL>` : shell to use as a script shebang `!#SHELL`. Default value is `/bin/bash`
- `--bg` : run the cell content in background. No output will be printed for this cell.
- `--amgr=<VAR>` : variable in user namespace to store backend object. Only way to get cell output when used with `--bg`.


### SSH example

SSH backend is not a workload manager but simply use ssh to reach executing resources. The ssh is not taking any standard input from user so it must connect without password or passphrase.

Specific arguments:

- `--host` : host to reach with ssh

```text
In [3]: %%execute --workloadmanager=ssh --host=adistantmachine
echo "Hello from $(hostname)"
...:
SSH started with pid: 10315
Running .
Done
Hello from adistantmachine
```


### Slurm example

Slurm backend to run cell content as slurm jobs. All parameters are passed to `sbatch` command.


```text
In [4]: %%execute -n8 -N1 --reservation=rsv --time=00:42:00
echo $SLURM_JOB_ID
srun -n 8 hostname
...:
Submitted batch job 957970
Running .
End batch job 957970 Status:  COMPLETED

957970
romeo141
romeo141
romeo141
romeo141
romeo141
romeo141
romeo141
romeo141
```


## Overriding installed configuration

A IPython profile specific configuration may be wanted for 'on-the-fly' generated profiles (associated to a specific usage). This configuration would override install parameters. To do so, inserts this kind of line in the `ipython_config.py` file of the profile:

```python
c.InteractiveShellApp.exec_lines = [
    'import execute_cell; execute_cell._DEFAULT_LINE_CMD_ARGS="--host=amachine"; execute_cell._DEFAULT_MGR="ssh"'
]
```
