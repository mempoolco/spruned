import os
from setuptools import setup, find_packages
import spruned


def read_pip_requirements():
    reqs = []
    with open(os.path.join(os.path.dirname(__file__), "requirements.txt"), 'r') as f:
        lines = f.readlines()
    for line in lines:
        line = line.strip()
        if '://' not in line:
            reqs.append(line)
    return reqs


def read_file(name):
    with open(name, 'r', encoding='utf-8') as f:
        file = f.read()
    return file


setup(
    name='spruned',
    version=spruned.__version__,
    url='https://github.com/gdassori/spruned/',
    license='MIT',
    author='Guido Dassori',
    author_email='guido.dassori@gmail.com',
    python_requires='>=3.5.2',
    description='Bitcoin Lightweight Pseudonode',
    long_description=read_file('README.rst'),
    install_requires=read_pip_requirements(),
    packages=find_packages(exclude=['htmlcov']),
    classifiers=[
        'Development Status :: 3 - Alpha',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
    ],
    entry_points={
        'console_scripts': [
            'spruned = spruned.app:main'
        ]
    },
    include_package_data=True
)
