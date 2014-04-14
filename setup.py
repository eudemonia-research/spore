#!/usr/bin/env python

from distutils.core import setup
from distutils.command.build_py import build_py as _build_py
from distutils.command.clean import clean as _clean
import subprocess, os, sys

protoc = "protoc"

def generate_proto(source):
  """Invokes the Protocol Compiler to generate a _pb2.py from the given
  .proto file.  Does nothing if the output already exists and is newer than
  the input."""

  output = source.replace(".proto", "_pb2.py")

  if (not os.path.exists(output) or
      (os.path.exists(source) and
       os.path.getmtime(source) > os.path.getmtime(output))):
    print("Generating %s..." % output)

    if not os.path.exists(source):
      sys.stderr.write("Can't find required file: %s\n" % source)
      sys.exit(-1)

    if protoc == None:
      sys.stderr.write(
          "protoc is not installed nor found in ../src.  Please compile it "
          "or install the binary package.\n")
      sys.exit(-1)

  protoc_command = [ protoc, "-I.", "--python_out=.", source ]
  if subprocess.call(protoc_command) != 0:
    sys.exit(-1)


class clean(_clean):
  def run(self):
    subprocess.call(["rm","spore/spore_pb2.py"])
    # _clean is an old-style class, so super() doesn't work.
    _clean.run(self)

class build_py(_build_py):
  def run(self):
    # Generate necessary .proto file if it doesn't exist.
    generate_proto("spore/spore.proto")

    # _build_py is an old-style class, so super() doesn't work.
    _build_py.run(self)

setup(name='spore',
      version='0.9.2',
      description='Simple P2P Framework',
      author='Kitten Tofu',
      author_email='kitten@eudemonia.io',
      url='http://eudemonia.io/spore/',
      packages=['spore'],
      cmdclass={'build_py': build_py, 'clean': clean},
     )
