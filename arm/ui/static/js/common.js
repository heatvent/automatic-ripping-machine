/*jshint multistr: true */
/*jshint esversion: 6 */
/*global $:false, jQuery:false */
/* jshint node: true */
/* jshint strict: false */

/* Job-card HTML and History helpers shared by Home and the job list. */
const MODEL_ID = "#exampleModal";
const DB_SUCCESS_BTN_ID = "#save-get-success";
const DB_FAIL_BTN_ID = "#save-get-failed";
const MSG_1_ID = "#message1 .alert-heading";
const SEARCH_BOX_ID = "#searchquery";
const MODAL_TITLE = ".modal-title";
const CARD_DECK = ".card-deck";
const SUCCESS_CLASS = "alert-success";
const MODAL_FOOTER = ".modal-footer";

function jobConfig(job) {
    if (job && job.config && typeof job.config === "object") {
        return job.config;
    }
    return {};
}

function getRipperName(job, idsplit) {
    let ripperName;
    if (job.ripper) {
        ripperName = job.ripper;
    } else {
        if (idsplit[0] === "0") {
            ripperName = "Local";
        } else {
            ripperName = "";
        }
    }
    return ripperName;
}

function addJobItem(job, authenticated) {
    // Local server or remote
    const idsplit = String(job.job_id).split("_");
    const jobHref = (idsplit[1] === undefined)
        ? `/jobdetail?job_id=${job.job_id}`
        : `${job.server_url}/jobdetail?job_id=${idsplit[1]}`;
    let x = `<div class="col-md-4" id="jobId${job.job_id}"><div class="card m-3 mx-auto">`;
    x += `<div class="card-header row no-gutters justify-content-center"><strong id="jobId${job.job_id}_header">${titleManual(job)}</strong></div>`;
    x += `<div class="job-card-body">`;
    x += `<div class="job-card-poster"><a href="${jobHref}">${posterCheck(job)}</a></div>`;
    x += buildMiddleSection(job);
    x += buildRightSection(job, idsplit, authenticated);
    x += playlistPickerHtml(job, idsplit);
    x += jobErrorsHtml(job);
    x += "</div></div></div>";
    return x;
}

function escapeHtml(text) {
    return String(text == null ? "" : text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

function jobErrorsHtml(job) {
    const errors = job && job.errors && job.errors !== "None" ? String(job.errors) : "";
    const hidden = errors ? "" : " hidden";
    return `<div class="job-card-warning alert alert-warning mb-0"${hidden} id="jobId${job.job_id}_errors" role="status">${escapeHtml(errors)}</div>`;
}

function transcodingCheck(job) {
    let x = "";
    const rippingBar = job.status === "ripping" && job.stage && job.progress;
    const transcodeBar = (job.status === "transcoding" || job.status === "waiting_transcode") && job.stage && job.progress;
    const musicBar = job.disctype === "music" && job.stage;
    if (rippingBar || transcodeBar || musicBar) {
        x += `<div id="jobId${job.job_id}_stage"><strong>Stage: </strong>${job.stage}</div>`;
        x += `<div id="jobId${job.job_id}_progress" >`;
        x += `<div class="progress">
                <div class="progress-bar progress-bar-striped progress-bar-animated" role="progressbar"
                aria-valuenow="${job.progress_round}" aria-valuemin="0" aria-valuemax="100"
                style="width: ${job.progress_round}%;">
                    <small class="justify-content-center d-flex position-absolute w-100">
                        ${job.progress}%
                    </small>
                </div>
              </div></div>`;
        x += `<div id="jobId${job.job_id}_eta"><strong>ETA: </strong>${job.eta}</div>`;
        if (transcodeBar) {
            x += `<div id="jobId${job.job_id}_cur_fps"><strong>CUR FPS: </strong>${job.cur_fps}</div>`;
            x += `<div id="jobId${job.job_id}_avg_fps"><strong>AVG FPS: </strong>${job.avg_fps}</div>`;
        }
    }
    // YYYY-MM-DD
    const d = new Date(Date.parse(job.start_time));
    const datestring = `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`

    x += `<strong>Start Date:</strong> ${datestring}<br>`;
    x += `<strong>Start Time:</strong> ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}<br>`;
    x += `<strong>Job Time:</strong> ${job.job_length === undefined ? "Ongoing" : job.job_length}<br>`;
    return x;
}

function isMusicJob(job) {
    return job.disctype === "music" || job.video_type === "Music";
}

function jobTypeLabel(job) {
    if (isMusicJob(job)) {
        return "Music";
    }
    return job.video_type;
}

function hasPosterUrl(job) {
    return Boolean(job.poster_url) &&
        job.poster_url !== "None" &&
        job.poster_url !== "N/A" &&
        job.poster_url !== "null";
}

function jobPosterSrc(job) {
    if (hasPosterUrl(job)) {
        return job.poster_url;
    }
    if (isMusicJob(job)) {
        return "/static/img/music.png";
    }
    return "/static/img/none.png";
}

function jobCoverClass(job, extraClass) {
    const classes = ["job-cover"];
    if (extraClass) {
        classes.push(extraClass);
    }
    if (isMusicJob(job)) {
        classes.push("job-cover-music");
    }
    return classes.join(" ");
}

function jobCoverHtml(job, extraClass, imgAttrs) {
    const id = imgAttrs && imgAttrs.id ? ` id="${imgAttrs.id}"` : "";
    return `<span class="${jobCoverClass(job, extraClass)}"><img${id} src="${jobPosterSrc(job)}" alt="" loading="lazy"></span>`;
}

function musicCheck(job, idsplit) {
    let x = "";
    if (!isMusicJob(job)) {
        x = `<a href="titlesearch?job_id=${idsplit[1]}" class="btn btn-sm btn-primary">Title Search</a>
             <a href="customTitle?job_id=${idsplit[1]}" class="btn btn-sm btn-primary">Custom Title</a>
             <a href="changeparams?config_id=${idsplit[1]}" class="btn btn-sm btn-primary">Edit Settings</a>`;
    }
    return x;
}

function posterCheck(job) {
    return jobCoverHtml(job, "job-cover-lg", {id: `jobId${job.job_id}_poster_url`});
}

const STATUS_LABELS = {
    success: "Success",
    fail: "Failed",
    waiting_manual: "Waiting for Title",
    waiting_playlist: "Pick Playlist",
    active: "Active",
    ripping: "Ripping",
    waiting: "Waiting",
    info: "Reading Disc",
    transcoding: "Transcoding",
    waiting_transcode: "Waiting to Transcode",
    yes: "Yes",
    no: "No",
};

function statusLabel(status, job) {
    if (job && job.tool_status) {
        return job.tool_status;
    }
    const raw = String(status == null ? "" : status);
    const key = raw.toLowerCase();
    const disc = String((job && (job.disctype || job.video_type)) || "").toLowerCase();
    const isMusic = disc === "music";
    if (isMusic && key === "info") {
        return "MusicBrainz";
    }
    if (isMusic && key === "ripping") {
        return "abcde";
    }
    if (key === "info") {
        return "Identify";
    }
    if (key === "ripping") {
        return "MakeMKV";
    }
    if (key === "transcoding") {
        return "HandBrake";
    }
    if (key === "waiting_transcode") {
        return "Waiting for HandBrake";
    }
    const mapped = STATUS_LABELS[key];
    if (mapped) {
        return mapped;
    }
    return raw.replace(/_/g, " ").replace(/\b\w/g, function (ch) {
        return ch.toUpperCase();
    });
}

function statusClass(status) {
    return "status-badge status-" + String(status || "").toLowerCase().replace(/\s+/g, "-");
}

function statusBadgeHtml(id, status, job) {
    const label = statusLabel(status, job);
    const raw = String(status == null ? "" : status);
    return `<span id="${id}" class="${statusClass(status)}" title="${label}" data-status="${raw}">${label}</span>`;
}

function titleManual(job) {
    const title = (job.title_manual && job.title_manual !== "None") ? job.title_manual : job.title;
    const year = (job.year && job.year !== "None") ? job.year : "";
    return year ? `${title} (${year})` : `${title}`;
}

function formatBytes(n) {
    let value = Number(n) || 0;
    const units = ["B", "KB", "MB", "GB", "TB"];
    let i = 0;
    while (value >= 1024 && i < units.length - 1) {
        value /= 1024;
        i += 1;
    }
    const shown = i === 0 ? String(Math.round(value)) : value.toFixed(1);
    return `${shown} ${units[i]}`;
}

function playlistPickerHtml(job, idsplit) {
    if (job.status !== "waiting_playlist") {
        return "";
    }
    const picks = Array.isArray(job.playlist_picks) ? job.playlist_picks : [];
    const jobId = idsplit[1];
    let rows = picks.map(function (pick) {
        const suggested = pick.suggested ? " <span class=\"playlist-suggested\">suggested</span>" : "";
        return `<button type="button" class="btn btn-sm btn-primary playlist-pick" data-job="${jobId}" data-track="${pick.track_number}">
            Title ${pick.track_number} · ${pick.length_hms || ""} · ${pick.chapters || 0} ch · ${formatBytes(pick.filesize)}${suggested}
        </button>`;
    }).join("");
    if (!rows) {
        rows = `<button type="button" class="btn btn-sm btn-primary playlist-pick" data-job="${jobId}" data-track="suggested">Use suggested title</button>`;
    }
    return `<div class="playlist-picker" id="jobId${job.job_id}_playlist">
        <div class="playlist-picker-label">This disc repeats the movie playlist. Pick a title, or ARM will use the suggested one in five minutes.</div>
        <div class="btn-group-vertical job-actions playlist-picks">${rows}
            <button type="button" class="btn btn-sm btn-secondary playlist-pick" data-job="${jobId}" data-track="all">Rip all similar titles</button>
        </div>
    </div>`;
}

function buildMiddleSection(job) {
    let x;
    x = "<div class=\"job-card-details\"><div class=\"card-body px-1 py-1\">";
    x += `<div id="jobId${job.job_id}_video_type"><strong>Type: </strong>${jobTypeLabel(job)}</div>`;
    x += `<div id="jobId${job.job_id}_devpath"><strong>Device: </strong>${job.devpath}</div>`;
    x += `<div><strong>Status: </strong>${statusBadgeHtml("jobId" + job.job_id + "_status", job.status, job)}</div>`;
    x += `<div id="jobId${job.job_id}_progress_section">${transcodingCheck(job)}</div></div></div>`;
    return x;
}

function onHomeJobList() {
    return Boolean(document.getElementById("joblist"));
}

function buildRightSection(job, idsplit, authenticated) {
    let x;
    if (idsplit[1] === undefined) {
        idsplit[0] = "0";
        idsplit[1] = job.job_id;
    }
    x = "<div class=\"job-card-side\">";
    x += `<div class="card-body px-2 py-1">`;
    const onHome = onHomeJobList();
    const showActions = onHome ? authenticated === true : true;
    if (showActions) {
        const hideRemote = onHome && idsplit[0] !== "0" ? "style=\"display: none;\"" : "";
        x += `<div class="btn-group-vertical job-actions" role="group" aria-label="buttons" ${hideRemote}>`;
        if (onHome) {
            x += `<button type="button" class="btn btn-sm btn-primary" data-toggle="modal" data-target="#exampleModal" data-type="abandon" data-jobid="${idsplit[1]}"
              data-href="json?job=${idsplit[1]}&mode=abandon">Abandon Job</button>
              <a href="logs?logfile=${job.logfile}&mode=full" class="btn btn-sm btn-primary">View Logfile</a>`;
        } else {
            x += `<button type="button" class="btn btn-sm btn-primary" data-toggle="modal" data-target="#exampleModal" data-type="delete" data-jobid="${idsplit[1]}"
              data-href="json?job=${idsplit[1]}&mode=delete">Delete Job</button>
              <a href="logs?logfile=${job.logfile}&mode=full" class="btn btn-sm btn-primary">View Logfile</a>`;
        }
        x += `</div>`;
    }
    x += `</div></div>`;
    return x;
}


function updateModal(modal, modalTitle = "", modalBody = "") {
    switch (actionType) {
        case "abandon":
            modalTitle = "Abandon This Job?";
            modalBody = "This item will be set to abandoned. You cannot set it back to active! Are you sure?";
            break;
        case "delete":
            modalTitle = "Delete This Job Forever?";
            modalBody = "This item will be permanently deleted and cannot be recovered. Are you sure?";
            break;
        case "fixperms":
            modalTitle = "Fix This Job's Folder Permissions?";
            modalBody = "This will try to set the chmod values from your arm.yaml. It wont always work, you may need to do this manually";
            break;
        case "search":
            modalTitle = "Search the Database";
            modalBody = `<div class="input-group mb-3"><div class="input-group-prepend"><span class="input-group-text" id="searchlabel">Search </span></div>
                       <input type="text" class="form-control" id="searchquery" aria-label="searchquery" name="searchquery" placeholder="Search...."
                       value="" aria-describedby="searchlabel"><div id="validationServer03Feedback" class="invalid-feedback">Search string too short.</div></div>`;
            break;
        default:
            modalTitle = "Do You Want to Leave This Page?";
            modalBody = "To view the log file you need to leave this page. Would you like to leave ?";
    }
    modal.find(".modal-title").text(modalTitle);
    modal.find(".modal-body").html(modalBody);
}


function hideModal() {
    $('#exampleModal').modal('hide');
    $('#message1').removeClass('d-none');
    $('#message2').addClass('d-none');
    $('#message3').addClass('d-none');
}
