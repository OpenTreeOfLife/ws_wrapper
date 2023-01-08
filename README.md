OpenTree Web-Services Wrapper
=============================

Getting Started
---------------

Change directory into your newly created project:

    cd ws_wrapper

Create a Python virtual environment:

    python3.8 -mvenv env

Python 3.9 should also work.

Install prerequisites:

    source env/bin/activate
    mkdir cruft
    cd cruft
    git clone git@github.com:OpenTreeOfLife/peyotl.git
    cd peyotl
    git checkout -b synth-on-demand origin/synth-on-demand
    pip install wheel
    pip install -r requirements.txt
    python ./setup.py develop
    cd ..
    git clone git@github.com:OpenTreeOfLife/propinquity.git
    cd propinquity
    git checkout -b synth-on-demand origin/chrono-and-on-demand
    pip install -r requirements.txt
    python ./setup.py develop
    cd ..
    git clone git@github.com:OpenTreeOfLife/otcetera.git
    cd otcetera
    git checkout -b synth-on-demand origin/taxonomy-diff-maker
    cd ..
    mkdir build-otc
    cd build-otc
    pip install meson


Follow the build instructions at 
https://github.com/OpenTreeOfLife/otcetera/blob/master/README.md
and install so that the `otc-...` tools 
(such as `otc-version-reporter`) are on your PATH.

    cd ../..

    

- Install the project in editable mode with its testing requirements.

    env/bin/pip install -e ".[testing]"

- Run your project's tests.

    env/bin/pytest

- Run your project.

    env/bin/pserve development.ini

