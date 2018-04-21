from setuptools import setup
import sys
sys.path.insert(0, '.')

if sys.version < '3.5.2':
    raise ValueError('Python >= 3.5.2 is required')

def read_pip_requirements():
    reqs = []
    with open('requirements.txt', 'r') as f:
        lines = f.readlines()
    for line in lines:
        line = line.strip()
        if '://' not in line:
            reqs.append(line)
        else:
            u, p = line.split('#egg=')
            p = p.replace('-', '==', 1)
            reqs.append(p)
    print(reqs)
    return reqs


def read_dependency_links():
    links = []
    with open('requirements.txt', 'r') as f:
        lines = f.readlines()
    for l in lines:
        line = l.strip()
        if '://' in line:
            links.append(line)
    res = []
    for link in links:
        link = link.replace('git+', '')
        res.append(link.replace('.git@spruned-support#', '/tarball/spruned-support#'))
    print(res)
    return res


setup(
    name='spruned',
    version='0.0.1',
    packages=['spruned'],
    url='https://github.com/gdassori/spruned/',
    license='MIT',
    author='Guido Dassori',
    author_email='guido.dassori@gmail.com',
    description='Bitcoin Lightweight Pseudonode',
    dependency_links=read_dependency_links(),
    install_requires=read_pip_requirements(),
)
