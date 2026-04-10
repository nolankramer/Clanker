#!/usr/bin/env bash
# Build a Clanker appliance OS image.
#
# Takes a base Ubuntu cloud image, mounts it, runs the provisioner
# inside it, and outputs a flashable .img.gz.
#
# Usage:
#   sudo ./build-image.sh                     # x86_64 (mini PCs)
#   sudo ./build-image.sh --arch arm64        # Raspberry Pi 5
#
# Requirements:
#   - Linux host with root access
#   - qemu-user-static (for cross-arch builds)
#   - wget, parted, losetup, mount, chroot
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
echo "Base image:   $BASE_URL"
echo "Output:       $OUTPUT_FILE.gz"
echo ""

# Must be root
if [ "$(id -u)" -ne 0 ]; then
    echo "Must be run as root (use sudo)"
    exit 1
fi

# Check dependencies
for cmd in wget qemu-img losetup mount chroot parted; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "Missing: $cmd — install it first"
        exit 1
    fi
done

# Cross-arch support
if [ "$ARCH" = "arm64" ] && [ "$(uname -m)" != "aarch64" ]; then
    if ! command -v qemu-aarch64-static &>/dev/null; then
        echo "Cross-arch build requires qemu-user-static"
        echo "Install: apt-get install qemu-user-static binfmt-support"
        exit 1
    fi
fi

mkdir -p "$OUTPUT_DIR" "$WORK_DIR"

# Download base image
BASE_IMG="$WORK_DIR/base-${ARCH}.img"
if [ ! -f "$BASE_IMG" ]; then
    echo "Downloading base image..."
    wget -q --show-progress -O "$BASE_IMG" "$BASE_URL"
fi

# Copy and resize
echo "Preparing image..."
cp "$BASE_IMG" "$OUTPUT_FILE"
qemu-img resize "$OUTPUT_FILE" "$IMAGE_SIZE"

# Mount the image
echo "Mounting image..."
LOOP=$(losetup --find --show --partscan "$OUTPUT_FILE")
PART="${LOOP}p1"

# Wait for partition to appear
sleep 1
if [ ! -b "$PART" ]; then
    # Try to detect the right partition
    partprobe "$LOOP" 2>/dev/null || true
    sleep 1
    PART="${LOOP}p1"
fi

# Resize filesystem to fill the image
e2fsck -f -y "$PART" 2>/dev/null || true
resize2fs "$PART" 2>/dev/null || true

MOUNTPOINT="$WORK_DIR/mnt"
mkdir -p "$MOUNTPOINT"
mount "$PART" "$MOUNTPOINT"

# Copy provisioner into the image
echo "Copying provisioner..."
mkdir -p "$MOUNTPOINT/opt/clanker-setup"
cp "$SCRIPT_DIR/provision.sh" "$MOUNTPOINT/opt/clanker-setup/provision.sh"
chmod +x "$MOUNTPOINT/opt/clanker-setup/provision.sh"

# Set up first-boot provisioning via cloud-init
mkdir -p "$MOUNTPOINT/var/lib/cloud/scripts/per-once"
cat > "$MOUNTPOINT/var/lib/cloud/scripts/per-once/clanker-provision.sh" << 'CLOUDINIT'
#!/bin/bash
# First-boot: run the Clanker provisioner
exec /opt/clanker-setup/provision.sh 2>&1 | tee /var/log/clanker-provision.log
CLOUDINIT
chmod +x "$MOUNTPOINT/var/lib/cloud/scripts/per-once/clanker-provision.sh"

# Set default user (clanker/clanker) for login
mkdir -p "$MOUNTPOINT/etc/cloud/cloud.cfg.d"
cat > "$MOUNTPOINT/etc/cloud/cloud.cfg.d/99-clanker.cfg" << 'CLOUDCFG'
system_info:
  default_user:
    name: clanker
    lock_passwd: false
    plain_text_passwd: clanker
    sudo: ALL=(ALL) NOPASSWD:ALL
    shell: /bin/bash

# Set hostname
hostname: clanker

# Grow the filesystem on first boot
growpart:
  mode: auto
  devices: [/]
resize_rootfs: true
CLOUDCFG

# Cleanup
echo "Unmounting..."
sync
umount "$MOUNTPOINT"
losetup -d "$LOOP"

# Compress
echo "Compressing image..."
gzip -f "$OUTPUT_FILE"

echo ""
echo "=== Done ==="
echo "Image: ${OUTPUT_FILE}.gz"
echo "Size:  $(du -sh "${OUTPUT_FILE}.gz" | cut -f1)"
echo ""
echo "Flash with: balena etcher, dd, or Raspberry Pi Imager"
echo "  dd if=${OUTPUT_FILE}.gz of=/dev/sdX bs=4M status=progress"
