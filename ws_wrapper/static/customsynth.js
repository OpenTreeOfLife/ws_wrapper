//var custom_server = 'http://127.0.0.1:1983'

var populate_table = function(by_key_obj) {
    var q_orders = [];
    var by_qo = {};
    for (const prop in by_key_obj) {
        var obj = by_key_obj[prop];
        var qo = obj.queue_order;
        q_orders[q_orders.length] = qo;
        by_qo[String(qo)] = obj;
    }
    q_orders.sort();
    var ctext;
    if (q_orders.length == 1) {
        ctext = "1 run is known"
    } else {
        ctext = q_orders.length + " runs are known"
    }
    var now = new Date();
    var days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
    var date =  days[now.getDay()] + " " + now.getDate() + " ";
    date += now.toLocaleString("default", {month: "long"}) + ', ';
    date += + now.getFullYear();
    var time = String(now.getHours()).padStart(2, "0");
    time += ":" + String(now.getMinutes()).padStart(2, "0");
    time += ":" + String(now.getSeconds()).padStart(2, "0");
    ctext += " as of " + time + " " + date + ".";
    $(".caption").text(ctext);
    var tab_el = $(".runtable");
    tab_el.empty();
    if (q_orders.length == 0) {
        return;
    }
    var h_row = tab_el.append("<tr>");
    h_row.append("<th>#</th>");
    h_row.append("<th>Collection</th>");
    h_row.append("<th>Root</th>");
    h_row.append("<th>Status</th>");
    h_row.append("<th>Synth ID</th>");
    for (var idx in q_orders) {
        var qo = q_orders[idx];
        var obj = by_qo[qo];
        var cur_row = tab_el.append("<tr>");
        cur_row.append("<td>" + qo +"</td>");
        cur_row.append("<td><a target=\"_blank\" href=\"https://tree.opentreeoflife.org/curator/collection/view/" + obj.collections + "\"> " + obj.collections +"</a></td>");
        cur_row.append("<td><a target=\"_blank\" href=\"https://tree.opentreeoflife.org/taxonomy/browse?id=" + obj.root_ott_id + "\">" + obj.root_ott_id + "</a></td>");
        var stat_text = "<td>" + obj.status;
        if (obj.status == "COMPLETED" || obj.status == "REDIRECTED") {
            stat_text += " <a href=\"" + obj.download_url + "\">download</a>";
        }
        stat_text += "</td>";
        cur_row.append(stat_text);
        cur_row.append("<td><font size=\"1\">" + obj.synth_id +"</font></td>");
    }
};

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
             populate_table(data);
      } 
   });
};

$(document).ready(function() {
    refresh_synth();
    $(".footnote").append("<br /><br /><br /><p>This is a testing/work-in-progress user-interface which "
    + "was built for <a href=\"https://opentreeoflife.github.io/SSBworkshop2023/\" target=\"_blank\">Open Tree's SSB 2023 Workshop</a>."
    + " This page is just a table-formatted version of the output you get from running:<br />"
    + "<pre>curl " + custom_server + '/v3/tree_of_life/list_custom_built_trees' + "</pre><br /></p>")
});