## Overview

This **heatvent-2x** tree is a fork of [Automatic Ripping Machine](https://github.com/automatic-ripping-machine/automatic-ripping-machine). Insert an optical disc (Blu-ray, DVD, CD) and ARM checks whether it's audio, video (Movie or TV), or data, then rips it.

See the [README](https://github.com/heatvent/automatic-ripping-machine/blob/heatvent-2x/README.md) for how this fork differs and how to install it. Original project origin story: https://b3n.org/automatic-ripping-machine


## Supported install

ARM on this fork runs as a **Docker image built from this source**. There is no Docker Hub image. Native Ubuntu/Debian install scripts from the original project are not supported here.

Due to the nature of Docker, the container can run on any Linux host that supports Docker (snap Docker is not supported). See [Docker.md](Docker.md) and the [README](https://github.com/heatvent/automatic-ripping-machine/blob/heatvent-2x/README.md).


## Get Started

[Getting Started](Getting-Started.md)

## Current Features

- Detects insertion of disc using udev
- Determines disc type...
  - If video (Blu-ray or DVD)
    - Retrieve title from disc or OMDb/TMDb API to name the folder "movie title (year)" so that Plex or Emby can pick it up
    - Determine if video is Movie or TV using OMDb or TMDb
    - Rip using MakeMKV, then optionally HandBrake or FFmpeg
    - Eject disc and queue transcoding when done
    - Transcoding jobs are asynchronously batched from ripping
    - Send notifications on updates via Apprise and others
  - If audio (CD) - rip using abcde (album lookup from MusicBrainz, CDDB, or CD-Text)
  - If data (Blu-Ray, DVD, or CD) - make an ISO backup
- Headless, designed to be run from a server
- Ripping from multiple optical drives in parallel
- HTML UI to interact with ripping jobs, view logs, and settings
