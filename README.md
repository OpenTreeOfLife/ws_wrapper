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


Non-public API
--------------

Some calls that could change their interface before we document them:

### build_tree

    curl  API_ENDPOINT/v3/tree_of_life/build_tree \
    -d '{"input_collection":"snacktavish/dros", \
       "root_id": "ott34905", \
       "if_no_phylo_flags": "extinct", \
       "cleaning_flags": "major_rank_conflict,major_rank_conflict_inherited,environmental,viral,barren,not_otu,was_container,inconsistent,hybrid,merged"}' 

`POST` to `v3/tree_of_life/build_tree`

Arguments:
  * `input_collection` the `username/coll_name` form of a valid collection fetchable from the phylesystem api
  * `root_id` the "ott###" form of the OTT ID to be the root of your "custom" synthesis
  * `cleaning_flags` comma-separated list of flags (if omitted synthesis defaults are used)
  * `if_no_phylo_flags` comma-separated list of flags (if omitted synthesis defaults are used)

Taxa that intersect with `cleaning_flags` are pruned during synthesis

Taxa that intersect with `if_no_phylo_flags` are pruned during synthesis if they are not found in an input phylogeny