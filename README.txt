OpenTree Web-Services Wrapper
=============================

Getting Started
---------------

- Change directory into your newly created project.

    cd ws_wrapper

- Create a Python virtual environment.

    python3 -m venv env

- Upgrade packaging tools.

    env/bin/pip install --upgrade pip setuptools

- Install peyotl

    source env/bin/activate
    cd ../peyotl
    python ./setup.py develop

- Install the project in editable mode with its testing requirements.

    env/bin/pip install -e ".[testing]"

- Run your project's tests.

    env/bin/pytest

- Run your project.

    env/bin/pserve development.ini


## Authorship
See CONTRIBUTORS.txt

JAR's contribution was the taxonomy/browse script in the opentree repository, which
was the basis for the taxonomy browsing code in this repository.