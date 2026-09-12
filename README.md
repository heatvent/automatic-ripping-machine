# Automatic Ripping Machine (heatvent-2x)

This is a maintained fork of the [Automatic Ripping Machine](https://github.com/automatic-ripping-machine/automatic-ripping-machine). Insert a Blu-ray, DVD, or CD and ARM identifies it, rips it, and (optionally) transcodes it.

Upstream project and origin story: [b3n.org/automatic-ripping-machine](https://b3n.org/automatic-ripping-machine).

**Branch:** `heatvent-2x`  
**Version:** 2.24.4 (this fork versions independently of upstream)

This is not the Docker Hub `automaticrippingmachine/automatic-ripping-machine` image. Build from this repository.

## Significant changes vs upstream

### User interface
- Dark gold theme, phone bottom nav, and grouped **Settings** (General including Web UI, Disk Drives, Movie Ripper, CD Ripper, Notifications, Maintenance, then System Information).
- Settings use plain-language labels, Yes/No and dropdowns, and help popovers that include the YAML key.
- API keys and passwords are masked in the UI. Login is required unless you turn it off.
- Job cards and Jobs no longer treat the text `None` as a real title or poster.

### Movie ripping (MakeMKV)
- **Main Title Only** (with Rip Method = MKV Titles) rips one guessed title instead of backing up the whole disc. Pick order: most chapters, then largest, then longest.
- Language / video / audio / subtitle dropdowns write MakeMKV’s default selection rule (`app_DefaultSelectionString`). Extra Arguments is only for real `makemkvcon` flags.
- Blu-rays that repeat the movie playlist many times get a **Possible playlist obfuscation** warning (notification + job). ARM cannot tell the real playlist from duration alone.
- MakeMKV license refresh can fail on a network error without aborting the job if a key is already on disk.

### CD ripping
- CD-R / CD-RW discs are treated as audio CDs when udev does not report an audio-track count.
- Audio CDs skip the ISO/UDF mount path. abcde is started non-interactively; album art is copied next to the FLACs.
- Empty-tray udev events do not start a rip.

### Reliability and files
- SQLite with WAL is the supported database. Do not switch this install to MySQL.
- Safer job/ffmpeg/eject paths, SQLite lock retries, and less duplicated `arm.log` noise.
- Filenames keep spaces, apostrophes, and commas; `:` becomes ` - `.
- The UI does not compare git hashes against upstream (upstream is still on a different 2.x line).

## Features (inherited)

- Detects disc insertion with udev
- Video (Blu-ray or DVD): title from the disc or OMDb/TMDb, MakeMKV rip, optional HandBrake or FFmpeg transcode, notifications (Apprise and others)
- Audio CD: abcde + MusicBrainz
- Data disc: ISO backup
- Several optical drives in parallel
- Headless; Python Flask UI for jobs, logs, and settings

## Usage

1. Insert disc
2. Wait for the disc to eject
3. Repeat

## Requirements

- Linux host that can run Docker (snap Docker is not supported)
- One or more optical drives
- Enough disk space for rips (a NAS is typical)

## Install

**Docker built from this repository is the only supported install.** There is no Docker Hub image for this fork, and native Ubuntu/Debian scripts from the original project are not supported here.

### 1. Host prep

Use a Linux user named `arm` in the `cdrom` and `video` groups. Confirm drives with `lsscsi -g`.

```bash
sudo apt install -y git docker.io lsscsi wget
sudo usermod -aG docker,cdrom,video arm
```

Log out and back in so group membership applies.

### 2. Clone and build

```bash
git clone --recurse-submodules -b heatvent-2x \
  https://github.com/heatvent/automatic-ripping-machine.git
cd automatic-ripping-machine
docker build -t automatic-ripping-machine:heatvent-2x .
```

Or run the installer (creates the `arm` user if needed, installs Docker, builds this branch, writes `~/start_arm_container.sh`):

```bash
wget https://raw.githubusercontent.com/heatvent/automatic-ripping-machine/heatvent-2x/scripts/installers/docker-setup.sh
chmod +x docker-setup.sh
sudo ./docker-setup.sh
```

### 3. Start the container

Copy `scripts/docker/start_arm_container.sh` (the installer already places one in `~arm`). Edit it:

- Set `ARM_UID` / `ARM_GID` from `id -u arm` and `id -g arm` (omit those lines if both are `1000`)
- Set `TZ` and `ARM_HOST_IP` to this machine’s LAN IPv4 (used in the UI and notifications)
- Point the volume paths at real host folders owned by `arm`
- Keep one `--device=/dev/srN:/dev/srN` line per optical drive from `lsscsi -g`
- Leave the image name `automatic-ripping-machine:heatvent-2x`

```bash
sudo ./start_arm_container.sh
```

Volumes (host path on the left, container path on the right):

| Container path | Purpose |
|---|---|
| `/home/arm` | Home, MakeMKV settings, SQLite database |
| `/home/arm/music` | Completed CD rips |
| `/home/arm/logs` | Logs |
| `/home/arm/media` | DVD/Blu-ray work and completed files (`raw`, `transcode`, `completed`) |
| `/etc/arm/config` | `arm.yaml`, `abcde.conf`, `apprise.yaml` |

### 4. First login

Open `http://<host-ip>:8080/setup` **only on a new database**. That page creates the admin user. Visiting `/setup` on an existing database can wipe it.

Default account (change it immediately):

- Username: `admin`
- Password: `password`

Then use **Settings** to set rip paths, MakeMKV language/audio/subtitles, and Main Title Only.

### Upgrading this fork

```bash
cd automatic-ripping-machine
git pull
docker build -t automatic-ripping-machine:heatvent-2x .
docker stop ARM   # or whatever --name you used
# re-run start_arm_container.sh with the same volumes
```

Do not `docker pull automaticrippingmachine/automatic-ripping-machine` expecting these changes.

More detail: [arm_wiki/Docker.md](arm_wiki/Docker.md), [arm_wiki/Docker-From-Source.md](arm_wiki/Docker-From-Source.md), and [arm_wiki/Getting-Started.md](arm_wiki/Getting-Started.md).

## Troubleshooting

Start with [arm_wiki/General-Troubleshooting.md](arm_wiki/General-Troubleshooting.md) and [arm_wiki/Docker-Troubleshooting.md](arm_wiki/Docker-Troubleshooting.md). Open issues on this repository: [heatvent/automatic-ripping-machine](https://github.com/heatvent/automatic-ripping-machine/issues).

The original project’s wiki and Discord describe the Docker Hub image, not this fork.

## Contributing

This repository is the fork. Open issues and pull requests here against `heatvent-2x`. Changes intended for everyone should also be offered upstream at [automatic-ripping-machine/automatic-ripping-machine](https://github.com/automatic-ripping-machine/automatic-ripping-machine).

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT License](LICENSE) (same as upstream).
