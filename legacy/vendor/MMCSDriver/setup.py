from setuptools import setup, find_packages

with open("README.md", encoding='utf-8') as fh:
    readme = fh.read()

setup(
    name="mmcs_driver",
    version="0.4.2",
    author="Xuandong Sun",
    author_email="",
    description="二代微波测控系统驱动",
    long_description=readme,
    packages=find_packages(),
    install_requires=[
        # List all the dependencies in this package.
        'numpy',
        'scipy',
        'matplotlib',
    ],
)
