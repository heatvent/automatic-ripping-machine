#!/usr/bin/env bash
set -eo pipefail

RED='\033[1;31m'
NC='\033[0m' # No Color

# This fork is built from GitHub, not pulled from Docker Hub.
GITHUB_REPO="${GITHUB_REPO:-heatvent/automatic-ripping-machine}"
GITHUB_BRANCH="${GITHUB_BRANCH:-heatvent-2x}"
IMAGE="${IMAGE:-automatic-ripping-machine:heatvent-2x}"

function usage() {
    echo -e "\nUsage: docker_setup.sh [OPTIONS]"
    echo -e " Builds the heatvent-2x ARM image from source (not Docker Hub)."
    echo -e " -b <branch>\tGit branch to build. Default is \"$GITHUB_BRANCH\""
    echo -e " -r <owner/repo>\tGitHub repo. Default is \"$GITHUB_REPO\""
    echo -e " -t <image>\tLocal image tag. Default is \"$IMAGE\""
}

while getopts 'b:r:t:h' OPTION
do
    case $OPTION in
    b)    GITHUB_BRANCH=$OPTARG
          ;;
    r)    GITHUB_REPO=$OPTARG
          ;;
    t)    IMAGE=$OPTARG
          ;;
    h)    usage
          exit 0
          ;;
    ?)    usage
          exit 2
          ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." 2>/dev/null && pwd || true)"

function install_reqs() {
    apt update -y && apt upgrade -y
    apt install -y curl git lsscsi
}

function add_arm_user() {
    echo -e "${RED}Adding arm user${NC}"
    if ! [[ "$(getent group arm)" ]]; then
        groupadd arm
    else
        echo -e "${RED}arm group already exists, skipping...${NC}"
    fi

    if ! id arm >/dev/null 2>&1; then
        useradd -m arm -g arm
        passwd arm
    else
        echo -e "${RED}arm user already exists, skipping...${NC}"
    fi
    usermod -aG cdrom,video arm
}

function launch_setup() {
    if [ -e /usr/bin/docker ]; then
        echo -e "${RED}Docker installation detected, skipping...${NC}"
        echo -e "${RED}Adding user arm to docker user group${NC}"
        usermod -aG docker arm
    else
        echo -e "${RED}Installing Docker${NC}"
        curl -sSL https://get.docker.com | bash
        echo -e "${RED}Adding user arm to docker user group${NC}"
        usermod -aG docker arm
    fi
}

function build_image() {
    local src=""
    if [ -f "${REPO_ROOT}/Dockerfile" ]; then
        src="${REPO_ROOT}"
        echo -e "${RED}Building ${IMAGE} from ${src}${NC}"
    else
        src="/tmp/arm-heatvent-src"
        echo -e "${RED}Cloning ${GITHUB_REPO}@${GITHUB_BRANCH} into ${src}${NC}"
        rm -rf "$src"
        git clone --recurse-submodules --depth 1 -b "$GITHUB_BRANCH" \
            "https://github.com/${GITHUB_REPO}.git" "$src"
        echo -e "${RED}Building ${IMAGE} from ${src}${NC}"
    fi
    docker build -t "$IMAGE" "$src"
    BUILD_SRC="$src"
}

function setup_mountpoints() {
    echo -e "${RED}Creating mount points${NC}"
    for dev in /dev/sr?; do
        mkdir -p "/mnt$dev"
    done
    if compgen -G "/mnt/dev/sr*" > /dev/null; then
        chown arm:arm /mnt/dev/sr*
    fi
}

function save_start_command() {
    local template="${BUILD_SRC}/scripts/docker/start_arm_container.sh"
    if [ ! -f "$template" ]; then
        echo "Missing start script template: $template" >&2
        exit 1
    fi
    cd ~arm
    if [ -e start_arm_container.sh ]; then
        echo -e "'start_arm_container.sh' already exists. Backing up..."
        sudo mv ./start_arm_container.sh ./start_arm_container.sh.bak
    fi
    sudo -u arm cp "$template" start_arm_container.sh
    chmod +x start_arm_container.sh
    sed -i "s|automatic-ripping-machine:heatvent-2x|${IMAGE}|" start_arm_container.sh
}

install_reqs
add_arm_user
launch_setup
build_image
setup_mountpoints
save_start_command

echo -e "${RED}Installation complete. Edit and run: $(echo ~arm)/start_arm_container.sh${NC}"
echo -e "${RED}Image: ${IMAGE}${NC}"
