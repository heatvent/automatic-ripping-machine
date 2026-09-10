/*jshint esversion: 6 */
/*global $:false */

let hrrref = "";
let activeJob = null;
let actionType = null;

function hideModal() {
    $(MODEL_ID).modal("hide");
}

function switchDelete() {
    $("#job-row-" + activeJob).remove();
    $(MSG_1_ID).html("Job was successfully deleted");
    hideModal();
    $("#message1").removeClass("d-none");
    setTimeout(function () {
        $("#message1").addClass("d-none");
    }, 5000);
}

function processFailedReturn(data) {
    $("#errorMessage").remove();
    $("#message3").removeClass("d-none").append(`<div id="errorMessage"><hr>Error: ${data.Error || data.error}</div>`);
    $(MODEL_ID).modal("hide");
    setTimeout(function () {
        $("#message3").addClass("d-none");
    }, 5000);
}

function jobRowHtml(job) {
    const title = (job.title_manual && job.title_manual !== "None") ? job.title_manual : (job.title || "Title unknown");
    const logfile = job.logfile || "";
    const logs = logfile
        ? `<a href="logs?logfile=${logfile}&mode=full">Full</a>
           <a href="logs?logfile=${logfile}&mode=armcat">ARM</a>
           <a href="logs?logfile=${logfile}&mode=tail">Live</a>
           <a href="logreader?logfile=${logfile}&mode=download">Download</a>`
        : "—";
    const badge = (typeof statusBadgeHtml === "function")
        ? statusBadgeHtml("status" + job.job_id, job.status)
        : (job.status || "");
    return `<tr id="job-row-${job.job_id}">
        <th scope="row" class="text-wrap"><a href="jobdetail?job_id=${job.job_id}">${title}</a></th>
        <td>${job.start_time || ""}</td>
        <td>${job.job_length || ""}</td>
        <td>${badge}</td>
        <td class="log-actions">${logs}</td>
        <td><button type="button" class="btn btn-sm btn-primary job-actions" data-toggle="modal"
            data-target="#exampleModal" data-type="delete" data-jobid="${job.job_id}"
            data-href="json?job=${job.job_id}&mode=delete">Delete</button></td>
    </tr>`;
}

function fillJobsTable(results, emptyMessage) {
    const tbody = $(".jobs-tbody");
    tbody.html("");
    const values = results ? Object.keys(results).map(function (key) { return results[key]; }) : [];
    if (values.length === 0) {
        $(MSG_1_ID).html(emptyMessage);
        $("#message1").removeClass("d-none");
        return;
    }
    values.forEach(function (job) {
        tbody.append(jobRowHtml(job));
    });
        $(MSG_1_ID).html("Matching rips");
    $("#message1").removeClass("d-none");
    setTimeout(function () {
        $("#message1").addClass("d-none");
    }, 4000);
}

function proccessReturn(data) {
    if (data.success) {
        if (data.mode === "delete") {
            switchDelete();
        } else if (data.mode === "search" || data.mode === "success" || data.mode === "fail") {
            fillJobsTable(data.results, "No rips match");
            hideModal();
        } else {
            hideModal();
        }
    } else {
        processFailedReturn(data);
    }
}

function runJobsQuery(href) {
    $.get(href, function (data) {
        proccessReturn(data);
    }, "json");
}

$(document).ready(function () {
    $("#save-get-success").on("click", function () {
        runJobsQuery("json?mode=getsuccessful");
    });
    $("#save-get-failed").on("click", function () {
        runJobsQuery("json?mode=getfailed");
    });
    $("#save-get-all").on("click", function () {
        window.location.href = "jobs";
    });
    $("#searchquery").on("keydown", function (event) {
        if (event.which === 13) {
            event.preventDefault();
            const q = $(SEARCH_BOX_ID).val() || "";
            if (q.length < 2) {
                $(SEARCH_BOX_ID).addClass("is-invalid");
                return;
            }
            $(SEARCH_BOX_ID).removeClass("is-invalid");
            runJobsQuery("json?mode=search&q=" + encodeURIComponent(q));
        }
    });
    $(MODEL_ID).on("show.bs.modal", function (event) {
        const button = $(event.relatedTarget);
        hrrref = button.data("href");
        activeJob = button.data("jobid");
        actionType = button.data("type");
        updateModal($(this));
    });
    $("#save-yes").on("click", function () {
        if (hrrref !== "") {
            $.get(hrrref, function (data) {
                proccessReturn(data);
            }, "json");
        }
    });
});
