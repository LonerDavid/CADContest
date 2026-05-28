"""Build script for eda_core C++ pybind11 extension."""

from pathlib import Path
from pybind11.setup_helpers import Pybind11Extension, build_ext
from setuptools import setup

ext = Pybind11Extension(
    "eda_core",
    sources=["cpp/eda_core/eda_core.cpp"],
    cxx_std=17,
    extra_compile_args=["-O3", "-march=native"],
)

setup(
    name="eda_core",
    version="1.0.0",
    ext_modules=[ext],
    cmdclass={"build_ext": build_ext},
)
