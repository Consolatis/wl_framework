# Make importing work for the root directory of the repo
from os.path import join, dirname
__path__.append(join(dirname(__file__), 'wl_framework'))

