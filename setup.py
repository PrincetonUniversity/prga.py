import os
from setuptools import setup, find_packages

# Utility function to read the README file.
def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()

setup(
        name = "prga",
        version = "0.3",
        author = "Ang Li",
        author_email = "angl@princeton.edu",
        description = "Princeton Reconfigurable Gate Array",
        url = "https://github.com/PrincetonUniversity/prga",
        packages = find_packages(exclude=["tests"]),
        include_package_data = True,
        long_description = read("README.md"),
        classifiers = [
            "Development Status :: 2 - Pre-Alpha",
            "Programming Language :: Python :: 2.7",
            "Programming Language :: Python :: 3.3",
            "Topic :: Scientific/Engineering :: Electronic Design Automation (EDA)",
            ],
        install_requires = ["future", "enum34", "jinja2", "lxml", "networkx", "bitarray"],
        setup_requires = ["pytest-runner"],
        tests_require = ["pytest"],
        )
