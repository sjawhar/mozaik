#!/usr/bin/env python
from distutils.core import setup

setup(
    name = "mozaik",
    version = "0.1.0",
    package_dir = {'mozaik': 'mozaik'},
    packages = ['mozaik',
                'mozaik.analysis',
                'mozaik.experiments',
                'mozaik.connectors',
                'mozaik.sheets',
                'mozaik.meta_workflow',
                'mozaik.models',
                'mozaik.models.vision',
                'mozaik.stimuli',
                'mozaik.stimuli.vision',
                'mozaik.storage',
                'mozaik.tools',
                'mozaik.visualization'
                ],
    author = "The Mozaik team",
    author_email = "antolikjan@gmail.com",
    description = "Python package mozaik is an integrated workflow framework for large scale neural simulations.",
    long_description = open('README.rst').read(),
    license = "CeCILL http://www.cecill.info",
    keywords = "computational neuroscience simulation large-scale model spiking",
    url = "http://neuralensemble.org/mozaik",
    classifiers = ['Development Status :: 3 - Alpha',
                   'Environment :: Console',
                   'Intended Audience :: Science/Research',
                   'License :: Other/Proprietary License',
                   'Natural Language :: English',
                   'Operating System :: OS Independent',
                   'Programming Language :: Python',
                   'Topic :: Scientific/Engineering'],
)
