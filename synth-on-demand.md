# Phylogenetic synthesis on demand



**Warning:** This API is in a very rough draft form. It will almost certainly change. 
It is being documented here for the benefit of communication between OT developers.

# Overview
Currently the synthesis is being run using https://github.com/OpenTreeOfLife/propinquity/tree/can-emit-dd-with-dev-merged
Documentation of that branch is poor, but the basic options are similar to the developement/main branches.

In this service, we anticipate the user to specify:
  1. a single username/collection combination to identify a collection in the  https://github.com/OpenTreeOfLife/collections-1/
repository. and
  2. an OTT ID for the root of the synthesis.

After completion, the synthesis output as a tar.gz will be available for download.

Currently, the testing form of this service is deployed on `ot38`


# Launching a synthesis:

verb = `POST`

URL = `https://API_ENDPOINT/v3/tree_of_life/build_tree`

Arguments via JSON object with:
  * "input_collection" -> a string of the form user/collection
  * "root_id": an OTT ID in ott# string form. 

### Example:

    curl -X POST https://API_ENDPOINT/v3/tree_of_life/build_tree -d '{"input_collection":"pcart/cnidaria", "root_id": "ott641033"}'

### Response
JSON object that represents a run status object for the run just initiated.
See the documentation of below for the run status object returned by the `list...` method.
The object returned by `build_tree` will be the current status of the single run just launched.
Hence it will hold the `synth_id` that serves as an identifier for this run.



# List known synth runs
verb = `GET`

URL = `https://API_ENDPOINT/v3/tree_of_life/list_custom_built_trees`


### Response
JSON object with every known  `synth_id` as a property value. Perhaps this should be a list instead of an object...

The value stored for each key is an "run status object" with the following properties:

  *  "synth_id": This is a unique key for the call that initiated the build.
  * "root_ott_id" - string form of the integer that is the OTT ID of the taxon that will be the root of the built tree. Any input tree will be pruned to just be the subtree of this taxon
  *  "collections": e.g."pcart/cnidaria" the name of the collection of input trees.
  *  "status": one of:
     * "QUEUED" - awaiting execution.
     * "RUNNING" - currently at the top of the queue and being analyzed by propinquity
     * "UNKNOWN" - this is triggered when the synth_id is not recognized. It could result if the synth was triggered on a different server (if we move to deploying this service in multiple locations, if the data store of custom synth runs has been purged of the old run referred to, or if a request is made to with an erroneous synth_id)
     * "REDIRECTED" - as the run began, propinquity noticed that this set of inputs had already been run. There will be a "redirect" -> higher-priority-synth-id in the response. The results can be seen by checking the that synth_id. 
     * "COMPLETED" - the run succeeded and the results can be downloaded.
     * "FAILED" - the run failed. At the present time, you will probably just need to contact the Open Tree of Life developers and tell them what synth_id you are interested in. We do not currently have good error reporting for this service which would enable debugging the errors by the client.
  * "exit_code": non-zero if the run failed
  * "download_url": if the runs is completed, this will be the URL for a tar.gz file of the output

Some addtional build parameters that are currently not under the user's control. are also included in the 
object. See propinquity documentation for their meaning. These include:

  * "cleaning_flags"
  * "additional_regrafting_flags": 
    
Finally, there are also some properties that are useful for OT developers for debugging, but not relevant to end-users. 
(These property names are likely to change, so they should not be viewed as part of the public API):
  * "opentree_home": "/work/opentree" - parent of the git-versioned code and data repos needed for propinquity
  * "ott_dir" - path to OTT on the server. Not accessible as that URL to clients, but the path often reveals the OTT version details 
  * "queue_order": # of where in the full queue this run was placed.
    

# Download the tree
verb = `GET`

URL - obtained from "download_url" of the `list...` call above, or via 
GET  https://API_ENDPOINT/v3/tree_of_life/list_custom_built_trees 
"/http://127.0.0.1:1983/v3/tree_of_life/custom_built_tree/pcart_cnidaria_641033_tmpn9dzbhow.tar.gz",
