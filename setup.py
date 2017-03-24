from distutils.core import setup
import os
import sys


def read(fname):
    """Read and join file content."""
    return open(os.path.join(os.path.dirname(__file__), fname)).read()

USER_DEFAULT_MGR = ""
USER_DEFAULT_CMD_ARGS = ""

args = sys.argv[:]
for arg in args:
    if arg.find('--workloadmanager=') == 0:
        USER_DEFAULT_MGR = arg.split('=')[1]
        sys.argv.remove(arg)
    if arg.find('--workloadmanagercmdargs=') == 0:
        USER_DEFAULT_CMD_ARGS = "=".join(arg.split('=')[1:])
        sys.argv.remove(arg)

default_val = {"default_manager": "'{0}'".format(USER_DEFAULT_MGR), }
# Parse the CMD_ARGS parameter as a python dictionnary
if USER_DEFAULT_CMD_ARGS.find('{') >= 0:
    default_val["default_cmd_args"] = str(eval(USER_DEFAULT_CMD_ARGS))
else:
    default_val["default_cmd_args"] = "'{0}'".format(USER_DEFAULT_CMD_ARGS)

with open("execute_batch_scheduler/__init__.py.in", "rt") as f:
    build_script_template = f.read()

build_script = build_script_template.format(**default_val)

with open("execute_batch_scheduler/__init__.py", "wt") as f:
    f.write(build_script)


setup(
    author="J-M Etancelin",
    author_email="jean-matthieu.etancelin@univ-reims.fr",
    description="Magics for cell execution through workload scheduler",
    long_description=read('README.md'),
    name="ipython-batch-scheduler-magic",
    packages=["execute_batch_scheduler", ],
    requires=["ipython"],
    url="NA",
    version="0.1",
    platforms=["Linux"],
    keywords=["Batch Scheduler", "Resource Manager", "IPython"],
)
