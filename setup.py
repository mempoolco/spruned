import os
import subprocess
from setuptools import setup, find_packages
import sys
from setuptools.command.install import install

sys.path.insert(0, '.')
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


def read_dependency_links():
    links = []
    with open(os.path.join(os.path.dirname(__file__), "requirements.txt"), 'r') as f:
        lines = f.readlines()
    for l in lines:
        line = l.strip()
        if '://' in line:
            links.append(line)
    return links


def read_file(name):
    with open(name, 'r', encoding='utf-8') as f:
        file = f.read()
    return file


class InstallGithubDepedenciesCommand(install):
    description = 'install github deps'

    def run(self):
        def install_github_dependencies():

            for dep in read_dependency_links():
                subprocess.call(['pip', 'install', '-e', dep])

        install_github_dependencies()
        install.run(self)


github_links = '\n- '.join(read_dependency_links())
github_libraries = '\n- '.join([x.split('#egg=')[1] for x in read_dependency_links()])
print('\nWarning! Know what you do!')
print('\nSpruned installer will also install custom dependencies from the following github links:\n\n-', github_links)
print('\nIs warmly advised to run spruned into a virtual environment, '
      'especially if you have installed the following libraries:\n\n-', github_libraries)
# Ouch, pip captured this. Find a way to inform the user on what's going on.

setup(
    cmdclass={
        'install': InstallGithubDepedenciesCommand,
    },
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
