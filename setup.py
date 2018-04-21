import os
from setuptools import setup, find_packages
import sys
sys.path.insert(0, '.')
import spruned

if sys.version < '3.5.2':
    raise ValueError('Python >= 3.5.2 is required')


def read_pip_requirements():
    reqs = []
    with open(os.path.join(os.path.dirname(__file__), "requirements.txt"), 'r') as f:
        lines = f.readlines()
    for line in lines:
        line = line.strip()
        if '://' not in line:
            reqs.append(line)
        else:
            u, p = line.split('#egg=')
            p = p.replace('-', '==', 1)
            reqs.append(p)
    return reqs


def read_dependency_links():
    links = []
    with open(os.path.join(os.path.dirname(__file__), "requirements.txt"), 'r') as f:
        lines = f.readlines()
    for l in lines:
        line = l.strip()
        if '://' in line:
            links.append(line)
    res = []
    for link in links:
        link = link.replace('git+', '')
        res.append(link.replace('.git@spruned-support#', '/tarball/spruned-support#'))
    return res


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
    dependency_links=read_dependency_links(),
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
    }
)
