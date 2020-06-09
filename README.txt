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

- Install prereqs

    pip install peyutil
    pip install nexson

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

## Caching
Since early June, 2020 we are trying out caching using the cachetools package.
The `data_cache_hasher` argument controls the behavior:
    If data_cache_hasher is None (default) the response is not cached.
    If not None, data_cache_hasher should be a callable that takes a data
    argument and returns a hashed data key or None.
    If the return value is None the cache is not used. If it is not None, then
    the cache will be checked for an entry for the hashed form of the tuple
    of (HTTP verb, url fragment, hashed data key).
Thus, it is vital that the hashed data key response is unique for every input
    that could change the response value. If an relevant argument is not included
    then the server may return the response for a previous, slightly different call.
