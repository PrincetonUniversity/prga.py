import os
from setuptools import setup, find_packages

# Utility function to read the README file.
def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()

setup(
        name = "prga",
        version = read("VERSION"),
        author = "Ang Li",
        author_email = "angl@princeton.edu",
        description = "Princeton Reconfigurable Gate Array",
        url = "https://github.com/PrincetonUniversity/prga",
        packages = find_packages(exclude=["tests"]),
        include_package_data = True,
        long_description = read("README.md"),
        classifiers = [
            "Development Status :: 2 - Pre-Alpha",
            "Programming Language :: Python :: 3.8",
            "Topic :: Scientific/Engineering :: Electronic Design Automation (EDA)",
            ],
        install_requires = ["future", "jinja2", "lxml", "networkx", "bitarray", "hdlparse", "cocotb"],
        setup_requires = ["pytest-runner"],
        tests_require = ["pytest"],
        )
