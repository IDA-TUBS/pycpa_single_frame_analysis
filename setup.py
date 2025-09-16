#!/usr/bin/env python

from setuptools import setup

setup(
    name='pycpa_single_frame_analysis',
    version='1.0',
    description='pyCPA synchronous analysis extension for large data objects',
    author='Jonas Peeck',
    author_email='peeck@ida.ing.tu-bs.de',
    url='https://github.com/IDA-TUBS/pycpa_single_frame_analysis',
    license='MIT',
    packages= ['pycpa_single_frame_analysis'],
    install_requires=['pycpa', 'networkx']
)
