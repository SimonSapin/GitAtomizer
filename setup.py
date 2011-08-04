from setuptools import setup

setup(
    name='GitAtomizer',
    version='0.1dev',
    license='BSD',
    author='Simon Sapin',
    author_email='simon.sapin@exyr.org',
    description='Builds an Atom feed for a git repository.',
    long_description='Builds an Atom feed of the latest commits in a git '
                     'repository, with full diffs.',
    platforms='any',
    install_requires=['dulwich'],
    py_modules=['gitatomizer'],
)
