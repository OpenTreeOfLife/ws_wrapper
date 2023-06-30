var do_submit = function() {
    var sub_btn = $("#submitbtn");
    var full_coll = ini_collection;
    $.ajax({
          url: custom_server + '/v3/tree_of_life/build_tree', 
          data: "{\"input_collection\": \"" + full_coll + "\", \"root_id\": \"ott" + ini_ott + "\"}",
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
          } 
       });
}

$(document).ready(function() {
    
    $(".footnote").append("<br /><br /><br /><p>This is a testing/work-in-progress user-interface which "
    + "was built for <a href=\"https://opentreeoflife.github.io/SSBworkshop2023/\" target=\"_blank\">Open Tree's SSB 2023 Workshop</a>."
    + " This page is an interface for running something like<br />"
    + "<font size=\"1\"><pre>curl -XPOST " + custom_server
    + "/v3/tree_of_life/build_tree \\<br/>"
    + "   -d \'{\"input_collection\": \"" + ini_collection 
    + "\", \"root_id\": \"ott" + ini_ott + "\"}\'"
    + "</pre></font><br /></p>")
});