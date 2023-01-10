var by_user = {};
var all_users = [];

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
    refresh_name_options()
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
    $(".footnote").append("<br /><br /><br /><p>This is a testing/work-in-progress user-interface which "
    + "was built for <a href=\"https://opentreeoflife.github.io/SSBworkshop2023/\" target=\"_blank\">Open Tree's SSB 2023 Workshop</a>."
    + " This page is an interface for running something like<br />"
    + "<font size=\"1\"><pre>curl " + custom_server
    + "/v3/tree_of_life/build_tree \\<br/>"
    + "   -d \'{\"input_collection\":\"snacktavish/dros\", \"root_id\": \"ott34905\"}\'"
    + "</pre></font><br /></p>")
});