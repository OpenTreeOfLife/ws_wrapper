var by_user = {};
var all_users = [];

var processed_ini_values = false;

var do_submit = function() {
    var sub_btn = $("#submitbtn");
    var u_inp_id = $("#userid");
    sub_btn.text("Submit Request");
    var uname = u_inp_id.find(":selected").text();
    if (!uname) {
        check_submit();
        return;
    }
    var cn_inp_id = $("#collname");
    var cname = cn_inp_id.find(":selected").text();
    if (!cname) {
        check_submit();
        return;
    }
    var tn_inp_id = $("#taxonname");
    var tname = tn_inp_id.val().trim();
    if (!tname) {
        check_submit();
        return;
    }
    var ott_id_str = $("#taxonid").val();
    const parsed = parseInt(ott_id_str, 10);
    if (isNaN(parsed)) {
        check_submit();
        return;
    }
    var full_coll = uname + "/" + cname;
    $.ajax({
          url: custom_server + '/v3/tree_of_life/build_tree', 
          data: "{\"input_collection\": \"" + full_coll + "\", \"root_id\": \"ott" + ott_id_str + "\"}",
          type:"POST",
          dataType:"json",
          // success: function (result) {alert("ok"); },
          error: function (err, status,thrown) {
                 //alert ("Error fetching taxon info for : " + ini_ott + " ERROR: " + err + " STATUS: " + status + " " + thrown );
          },
          complete: function (xhr, status) { 
            if (xhr.status == 200) {
                data = $.parseJSON(xhr.responseText);
                var url_str = custom_server + '/v3/tree_of_life/browse_custom';
                url_str += '?synth_id=' + data.synth_id;
                location.href = url_str;
            }
            check_submit();
          } 
       });
}

var check_submit = function() {
    var sub_btn = $("#submitbtn");
    var u_inp_id = $("#userid");
    sub_btn.text("Submit Request");
    var uname = u_inp_id.find(":selected").text();
    if (!uname) {
        sub_btn.prop("disabled", true);
        return;
    }
    var cn_inp_id = $("#collname");
    var cname = cn_inp_id.find(":selected").text();
    if (!cname) {
        sub_btn.prop("disabled", true);
        return;
    }
    var tn_inp_id = $("#taxonname");
    var tname = tn_inp_id.val().trim();
    if (!tname) {
        sub_btn.prop("disabled", true);
        return;
    }
    var ott_id_str = $("#taxonid").val();
    const parsed = parseInt(ott_id_str, 10);
    if (isNaN(parsed)) {
        sub_btn.prop("disabled", true);
        return;
    }
    sub_btn.removeAttr("disabled");
    sub_btn.text("Request build for coll=\"" + uname + "/" + cname + "\" ott_id=" + ott_id_str);
    return;
}

var ott_id_edit = function(ott_id) {
    $.ajax({
          url: 'https://api.opentreeoflife.org/v3/taxonomy/taxon_info', 
          data: "{\"ott_id\":" + ott_id+"}",
          type:"POST",
          dataType:"json",
          // success: function (result) {alert("ok"); },
          error: function (err, status,thrown) {
                 //alert ("Error fetching taxon info for : " + ini_ott + " ERROR: " + err + " STATUS: " + status + " " + thrown );
          },
          complete: function (xhr, status) { 
            if (xhr.status == 200) {
                data = $.parseJSON(xhr.responseText);  
                $("#taxonname").val(data.name);
                $("#taxonid").val(String(data.ott_id));
            } else {
                $("#taxonname").val("");
            }
            check_submit();
          } 
       });
};

var alterOttID = function() {
    var tax_id_el = $('#taxonid');
    var cur_ott_id = tax_id_el.val().trim();
    const parsed = parseInt(cur_ott_id, 10);
    if (isNaN(parsed)) {
        tax_id_el.val("");
        check_submit();
        return;
    }
    ott_id_edit(parsed);
};

var process_ini = function() {
    if (ini_coll_user) {
        var uiel = $('#userid option');
        var lc = ini_coll_user.toLowerCase();
        uiel.each(function(i, el) { 
            var x = el.text.toLowerCase();
            //console.log(x);
            if (x == lc) {
                $(this).prop('selected', true);
                refresh_name_options();
            }
        });
    }
    if (ini_coll_name) {
        var uiel = $('#collname option');
        var lc = ini_coll_name.toLowerCase();
        uiel.each(function(i, el) { 
            var x = el.text.toLowerCase();
            //console.log(x);
            if (x == lc) {
                $(this).prop('selected', true);
            }
        });
    }
    if (ini_ott) {
        ott_id_edit(ini_ott);
    }
    processed_ini_values = true;
};

// autocomplete name logic taken from Jim Allman's code
//      from opentree/webapps/views/layout.html

/* Sensible autocomplete behavior requires the use of timeouts
 * and sanity checks for unchanged content, etc.
 */
clearTimeout(searchTimeoutID);  // in case there's a lingering search from last page!
var searchTimeoutID = null;
var searchDelay = 1000; // milliseconds
var hopefulSearchName = null;
var showingResultsForSearchText = null;
function setTaxaSearchFuse(e) {
    if (searchTimeoutID) {
        // kill any pending search, apparently we're still typing
        clearTimeout(searchTimeoutID);
    }
    // reset the timeout for another n milliseconds
    searchTimeoutID = setTimeout(searchForMatchingTaxa, searchDelay);

    /* If the last key pressed was the ENTER key, stash the current (trimmed)
     * string and auto-jump if it's a valid taxon name.
     */
    if (e.type === 'keyup') {
        $("#taxonid").val("");
        switch (e.which) {
            case 13:
                hopefulSearchName = $('input[name=taxon-search]').val().trim();
                jumpToExactMatch();  // use existing menu, if found
                break;
            case 17:
                // do nothing (probably a second ENTER key)
                break;
            case 39:
            case 40:
                // down or right arrow should try to tab to first result
                $('#search-results a:eq(0)').focus();
                break;
            default:
                hopefulSearchName = null;
        }
    } else {
        hopefulSearchName = null;
    }
}

var ott_selected = function(selected) {
//    var searchText = $input.val().trimLeft();
//    var srel = $('#search-results');
};

var searchForMatchingTaxa = function searchForMatchingTaxa() {
    // clear any pending search timeout and ID
    clearTimeout(searchTimeoutID);
    searchTimeoutID = null;
    var $input = $('input[name=taxon-search]');
    var searchText = $input.val().trimLeft();
    var srel = $('#search-results');
    if (searchText.length === 0) {
        srel.html('');
        if (typeof snapViewerFrameToMainTitle === 'function') snapViewerFrameToMainTitle();
        return false;
    } else if (searchText.length < 2) {
        srel.html('<li class="disabled"><a><span class="text-error">Enter two or more characters to search</span></a></li>');
        srel.dropdown('toggle');

        if (typeof snapViewerFrameToMainTitle === 'function') snapViewerFrameToMainTitle();
        return false;
    }

    // groom trimmed text based on our search rules
    //var searchContextName = $('select[name=taxon-search-context]').val();
    var searchContextName = "All life";
    // is this unchanged from last time? no need to search again..
    if ((searchText == showingResultsForSearchText) && (searchContextName == showingResultsForSearchContextName)) {
        ///console.log("Search text and context UNCHANGED!");
        return false;
    }

    // stash these to use for later comparison (to avoid redundant searches)
    var queryText = searchText; // trimmed above
    var queryContextName = searchContextName;
    srel.html('<li class="disabled"><a><span class="text-warning">Search in progress...</span></a></li>');
    srel.dropdown('toggle');
    if (typeof snapViewerFrameToMainTitle === 'function') snapViewerFrameToMainTitle();

    $.ajax({
        url: doTNRSForAutocomplete_url,  // NOTE that actual server-side method name might be quite different!
        type: 'POST',
        dataType: 'json',
        data: JSON.stringify({
            "name": searchText,
            "context_name": searchContextName
        }),  // data (asterisk required for completion suggestions)
        crossDomain: true,
        contentType: 'application/json',
        success: function(raw_data) {    // JSONP callback
            // stash the search-text used to generate these results
            showingResultsForSearchText = queryText;
            showingResultsForSearchContextName = queryContextName;

            srel.html('');
            var maxResults = 100;
            var visibleResults = 0;
            /*
             * The returned JSON 'data' is a simple list of objects. Each object is a matching taxon (or name?)
             * with these properties:
             *      ott_id         // taxon ID in OTT taxonomic tree
             *      unique_name    // the taxon name, or unique name if it has one
             *      is_higher      // points to a genus or higher taxon? T/F
             */
            var data = []
            for (var idx in raw_data) {
                var datum = raw_data[idx]
                if (datum.is_higher) {
                    data[data.length] = datum;
                }
            }
            var rq = '';
            var uname = $("#userid").find(":selected").text();
            if (uname) {
                rq += '&coll_user=' + uname;
            }
            var cname = $("#collname").find(":selected").text();
            if (cname) {
                rq += '&coll_name=' + cname;
            }
            if (data && data.length && data.length > 0) {
                // Sort results to show exact match(es) first, then higher taxa, then others
                // initial sort on higher taxa (will be overridden by exact matches).
                // N.B. As of the v3 APIs, an exact match will be returned as the only result.
                data.sort(function(a,b) {
                    if (a.is_higher === b.is_higher) return 0;
                    if (a.is_higher) return -1;
                    if (b.is_higher) return 1;
                });

                // show all sorted results, up to our preset maximum
                var matchingNodeIDs = [ ];  // ignore any duplicate results (point to the same taxon)
                for (var mpos = 0; mpos < data.length; mpos++) {
                    if (visibleResults >= maxResults) {
                        break;
                    }
                    var match = data[mpos];
                    var matchingName = match.unique_name;
                    var matchingID = match.ott_id;
                    if ($.inArray(matchingID, matchingNodeIDs) === -1) {
                        // we're not showing this yet; add it now
                        srel.append(
                            //'<li><a href="'+ matchingID +'" tabindex="'+ (mpos+2) +'">'+ matchingName +'</a></li>'
                            '<li><a href="/v3/tree_of_life/launch_custom?ott='+ matchingID + rq + '" tabindex="'+ (mpos+2) +'">'+ matchingName +'</a></li>'
                        );
                        matchingNodeIDs.push(matchingID);
                        visibleResults++;
                    }
                }

                $('#search-results a')
                    .click(function(e) {
                        // suppress normal dropdown logic and jump to link normally (TODO: Why is this needed?)
                        e.stopPropagation();
                        ott_selected(e);
                    })
                    .each(function() {
                        //var $link = $(this);
                        // //// WAS constructed literal ('/opentree/'+ "ottol" +'@'+ itsNodeID +'/'+ itsName)
                        // var safeURL = historyStateToURL({
                        //     nodeID: $link.attr('href'),
                        //     domSource: 'ottol',
                        //     nodeName: makeSafeForWeb2pyURL($link.text()),
                        //     viewer: 'argus'
                        // });
                        // $link.attr('href', safeURL);
                        //
                    });
                $('#search-results').dropdown('toggle');

                
            } else {
                $('#search-results').html('<li class="disabled"><a><span class="muted">No results for this search</span></a></li>');
                $('#search-results').dropdown('toggle');
            }
            if (typeof snapViewerFrameToMainTitle === 'function') snapViewerFrameToMainTitle();
        },
        error: function(jqXHR, textStatus, errorThrown) {
            // report errors or malformed data, if any (else ignore)
            if (textStatus !== 'success') {
                if (jqXHR.status >= 500) {
                    // major TNRS error! offer the raw response for tech support
                    var errMsg = jqXHR.statusText +' ('+ jqXHR.status +') searching for<br/>'
+'<strong style="background-color: #edd; padding: 0 3px; margin: 0 -3px;">'+ queryText +'</strong><br/>'
+'Please modify your search and try again.<br/>'
+'<span class="detail-toggle" style="text-decoration: underline !important;">Show details</span>'
+'<pre class="error-details" style="display: none;">'+ jqXHR.responseText +' [auto-parsed]</pre>';
                    //showErrorMessage(errMsg);
                    $('#search-results').html('<li class="disabled"><a><span style="color: #933;">'+ errMsg +'</span></a></li>');
                    $('#search-results').find('span.detail-toggle').click(function(e) {
                        e.preventDefault();
                        $(this).next('.error-details').show()
                        return false;
                    });
                    $('#search-results').dropdown('toggle');
                }
            }
            return;
        }
    });
    return false;
}


var refresh_name_options = function() {
    var u_inp_id = $("#userid");
    var uname = u_inp_id.find(":selected").text();
    var cnlist = []
    if (by_user.hasOwnProperty(uname)) {
        cnlist = by_user[uname];
    }
    var cn_inp_id = $("#collname");
    cn_inp_id.empty();
    for (var idx in cnlist) {
        var cname = cnlist[idx];
        cn_inp_id.append("<option value=\"" + cname + "\">" + cname +"</option>")
    }
};

var populate_dropdown = function(coll_id_list) {
    by_user = {};
    all_users = [];
    for (var idx in coll_id_list) {
        var coll_id = coll_id_list[idx];
        const sci = coll_id.split("/");
        if (sci.length != 2) {
            continue;
        }
        var user = sci[0];
        var coll_name = sci[1];
        if (by_user.hasOwnProperty(user)) {
            var cn_list = by_user[user];
            cn_list[cn_list.length] = coll_name;
        } else {
            by_user[user] = [coll_name];
            all_users[all_users.length] = user;
        }
    }
    all_users.sort();
    for (const u in by_user) {
        var nlist = by_user[u];
        nlist.sort();
    }

    var ctext = coll_id_list.length + " collections are known";
    var now = new Date();
    var days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
    var date =  days[now.getDay()] + " " + now.getDate() + " ";
    date += now.toLocaleString("default", {month: "long"}) + ', ';
    date += + now.getFullYear();
    var time = String(now.getHours());
    time += ":" + String(now.getMinutes()).padStart(2, "0");
    time += ":" + String(now.getSeconds()).padStart(2, "0");
    ctext += " as of " + time + " " + date + ".";
    $(".caption").text(ctext);
    var u_inp_id = $("#userid");
    u_inp_id.empty();
    for (var idx in all_users) {
        var uname = all_users[idx];
        u_inp_id.append("<option value=\"" + uname + "\">" + uname +"</option>")
    }
    refresh_name_options();
    if (!processed_ini_values) {
        process_ini();
    }
};

var refresh_collections = function() {
    $.ajax({
      url: 'https://api.opentreeoflife.org/v3/collections/collection_list', 
      // data: ,
      type:"GET",
      dataType:"json",
      // success: function (result) {alert("ok"); },
      error: function (err, status,thrown) {
             alert ("Error fetching list of custom trees: " + " ERROR: " + err + " STATUS: " + status + " " + thrown );
      },
      complete: function (xhr, status) { 
             data = $.parseJSON(xhr.responseText);  
             populate_dropdown(data);
      } 
   });
};



$(document).ready(function() {
    refresh_collections();
    $('input[name=taxon-search]').unbind('keyup change').bind('keyup change', setTaxaSearchFuse );
    $('#taxon-search-form').unbind('submit').submit(function() {
        searchForMatchingTaxa();
        return false;
    });
    $('#taxonid').unbind('keyup change').bind('keyup change', alterOttID );
    

    
    $(".footnote").append("<br /><br /><br /><p>This is a testing/work-in-progress user-interface which "
    + "was built for <a href=\"https://opentreeoflife.github.io/SSBworkshop2023/\" target=\"_blank\">Open Tree's SSB 2023 Workshop</a>."
    + " This page is an interface for running something like<br />"
    + "<font size=\"1\"><pre>curl -XPOST " + custom_server
    + "/v3/tree_of_life/build_tree \\<br/>"
    + "   -d \'{\"input_collection\":\"snacktavish/dros\", \"root_id\": \"ott34905\"}\'"
    + "</pre></font><br /></p>")
});