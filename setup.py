from setuptools import setup, find_packages

setup(
    name="plm-spread",
    version="0.1.0",
    author="noxindeed",
    description="Depth-weighted spread profiler for Polymarket order books",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    python_requires=">=3.8",
    install_requires=["requests"],
    py_modules=["pmspread"],
    entry_points={
        "console_scripts": [
            "pmspread=pmspread:main",
        ],
    },
)