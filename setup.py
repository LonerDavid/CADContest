"""Build script for eda_core C++ pybind11 extension."""

from pathlib import Path
from pybind11.setup_helpers import Pybind11Extension, build_ext
from setuptools import setup

ext = Pybind11Extension(
    "eda_core",
    sources=["cpp/eda_core/eda_core.cpp"],
    cxx_std=17,
    # -O3 only: portable across any x86-64 node. Avoid -march=native so the
    # built .so cannot hit "Illegal instruction" if the eval node's CPU differs
    # from the build node.
    extra_compile_args=["-O3"],
)

setup(
    name="eda_core",
    version="1.0.0",
    ext_modules=[ext],
    cmdclass={"build_ext": build_ext},
)
