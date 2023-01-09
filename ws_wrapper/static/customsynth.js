var custom_server = 'http://127.0.0.1:1983'

var refresh_synth = function() {
    $.ajax({
      url: custom_server + '/v3/tree_of_life/list_custom_built_trees', 
      // data: ,
      type:"GET",
      dataType:"json",
      // success: function (result) {alert("ok"); },
      error: function (err, status,thrown) {
             alert ("Error fetching list of custom trees: " + " ERROR: " + err + " STATUS: " + status + " " + thrown );
      },
      complete: function (xhr, status) { 
             data = $.parseJSON(xhr.responseText);  
             alert (data);
      } 
   });
}

$(document).ready(function() {
    refresh_synth();
});