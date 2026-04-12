#!/usr/bin/env bash
# Build a Clanker appliance OS image.
#
# Creates a flashable Ubuntu-based image with Docker, HA, Ollama,
# and Clanker pre-installed. First boot launches the web setup wizard
# at http://clanker.local.
#
# For HA OS users: use the HA Add-on instead (no custom image needed).
# This image is for users who want a dedicated Clanker appliance
# running on bare metal (mini PC, NUC, etc.).
#
# Usage:
#   sudo ./build-image.sh                     # x86_64 (mini PCs)
#   sudo ./build-image.sh --arch arm64        # Raspberry Pi 5
#
# Output:
#   image/output/clanker-<arch>-<date>.img.gz
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARCH="${1:-x86_64}"
DATE="$(date +%Y%m%d)"
OUTPUT_DIR="$SCRIPT_DIR/output"
WORK_DIR="$SCRIPT_DIR/.work"
IMAGE_SIZE="8G"

# Ubuntu 24.04 cloud image URLs
declare -A BASE_IMAGES=(
    ["x86_64"]="https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img"
    ["arm64"]="https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-arm64.img"
)

if [[ "$1" == "--arch" ]]; then
    ARCH="$2"
fi

BASE_URL="${BASE_IMAGES[$ARCH]:-}"
if [ -z "$BASE_URL" ]; then
    echo "Unknown arch: $ARCH (supported: x86_64, arm64)"
    exit 1
fi

OUTPUT_FILE="$OUTPUT_DIR/clanker-${ARCH}-${DATE}.img"

echo "=== Clanker Image Builder ==="
echo "Architecture: $ARCH"
echo "Output:       $OUTPUT_FILE.gz"

if [ "$(id -u)" -ne 0 ]; then
    echo "Must be run as root (use sudo)"
    exit 1
fi

for cmd in wget qemu-img losetup mount chroot; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "Missing: $cmd"
        exit 1
    fi
done

if [ "$ARCH" = "arm64" ] && [ "$(uname -m)" != "aarch64" ]; then
    if ! command -v qemu-aarch64-static &>/dev/null; then
        echo "Cross-arch build requires qemu-user-static"
        exit 1
    fi
fi

mkdir -p "$OUTPUT_DIR" "$WORK_DIR"

# Download base image
BASE_IMG="$WORK_DIR/base-${ARCH}.qcow2"
if [ ! -f "$BASE_IMG" ]; then
    echo "Downloading base image..."
    wget -q --show-progress -O "$BASE_IMG" "$BASE_URL"
fi

# Convert and resize
echo "Converting and resizing image..."
qemu-img convert -f qcow2 -O raw "$BASE_IMG" "$OUTPUT_FILE"
qemu-img resize -f raw "$OUTPUT_FILE" "$IMAGE_SIZE"

echo "Expanding partition..."
echo ", +" | sfdisk -N 1 "$OUTPUT_FILE" 2>/dev/null || true

# Mount
echo "Mounting image..."
LOOP=$(losetup --find --show --partscan "$OUTPUT_FILE")
udevadm settle 2>/dev/null || sleep 2

PART=""
for p in "${LOOP}p1" "${LOOP}p2"; do
    if [ -b "$p" ]; then
        FSTYPE=$(blkid -s TYPE -o value "$p" 2>/dev/null || true)
        if [ "$FSTYPE" = "ext4" ]; then
            PART="$p"
            break
        fi
    fi
done

if [ -z "$PART" ]; then
    echo "ERROR: Could not find ext4 partition"
    losetup -d "$LOOP"
    exit 1
fi

e2fsck -f -y "$PART" 2>/dev/null || true
resize2fs "$PART" 2>/dev/null || true

MOUNTPOINT="$WORK_DIR/mnt"
mkdir -p "$MOUNTPOINT"
mount "$PART" "$MOUNTPOINT"

# Copy provisioner
echo "Copying provisioner..."
mkdir -p "$MOUNTPOINT/opt/clanker-setup"
cp "$SCRIPT_DIR/provision.sh" "$MOUNTPOINT/opt/clanker-setup/provision.sh"
chmod +x "$MOUNTPOINT/opt/clanker-setup/provision.sh"

# Cloud-init first boot
mkdir -p "$MOUNTPOINT/var/lib/cloud/scripts/per-once"
cat > "$MOUNTPOINT/var/lib/cloud/scripts/per-once/clanker-provision.sh" << 'CLOUDINIT'
#!/bin/bash
exec /opt/clanker-setup/provision.sh 2>&1 | tee /var/log/clanker-provision.log
CLOUDINIT
chmod +x "$MOUNTPOINT/var/lib/cloud/scripts/per-once/clanker-provision.sh"

# Default user
mkdir -p "$MOUNTPOINT/etc/cloud/cloud.cfg.d"
cat > "$MOUNTPOINT/etc/cloud/cloud.cfg.d/99-clanker.cfg" << 'CLOUDCFG'
system_info:
  default_user:
    name: clanker
    lock_passwd: false
    plain_text_passwd: clanker
    sudo: ALL=(ALL) NOPASSWD:ALL
    shell: /bin/bash
hostname: clanker
growpart:
  mode: auto
  devices: [/]
resize_rootfs: true
CLOUDCFG

# Cleanup
sync
umount "$MOUNTPOINT"
losetup -d "$LOOP"

echo "Compressing image..."
gzip -f "$OUTPUT_FILE"

echo ""
echo "=== Done ==="
echo "Image: ${OUTPUT_FILE}.gz"
echo "Size:  $(du -sh "${OUTPUT_FILE}.gz" | cut -f1)"
echo ""
echo "Flash with Balena Etcher or:"
echo "  gunzip -c ${OUTPUT_FILE}.gz | sudo dd of=/dev/sdX bs=4M status=progress"
