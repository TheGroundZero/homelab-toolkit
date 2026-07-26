Implementation notes for System A and System B
=============================================

Overview
--------

This project contains templates and scripts to provision:

- System A: Fedora CoreOS (Ignition) running Podman quadlets; 4 NICs mapped to physical networks (DMZ, IOT, NOT, and one to be decided). Caddy is the only one exposed on DMZ.
- System B: Debian host running Frigate container via Podman with a Coral USB accelerator. System B connects to CAMERA physical network and IOT via VLAN 30.

Key files added
---------------

- scripts/apps.yaml                             -> Annotated Quadlet configs for containers on System A
- .config/containers/systemd/homelab.network    -> Quadlet network template for inter-container connectivity on System A
- scripts/apps-frigate.yaml                     -> Quadlet config for Frigate on System B
- .config/containers/systemd/camera.network     -> Quadlet network template for Frigate on System B
- homelab/frigate/frigate.yml.example           -> Example Frigate config
- homelab/frigate/frigate.env.example           -> Example env template
- IMPLEMENTATION.md                             -> This file

Network & addressing
--------------------

- System A NICs are physically wired to distinct networks at the switch. Do not configure static IPs in Ignition; rely on DHCP on each interface.
- Fedora Cora OS (System A) uses predictable interface names per systemd.net-naming-scheme by default. For example: enp5s0
- System B is physically on CAMERA network and uses VLAN 30 to reach IOT. Ensure the host's VLAN interface (e.g., eth0.30) is present and DHCP-enabled.

Coral USB passthrough (System B - Debian)
----------------------------------------

1. Install dependencies:
   sudo apt update && sudo apt install -y libusb-1.0-0-dev usbutils
2. Create a udev rule for Coral (example):
   /etc/udev/rules.d/99-edgetpu.rules
   ACTION=="add", SUBSYSTEM=="usb", ATTR{idVendor}=="18d1", ATTR{idProduct}=="9302", MODE="0666"
   \# Verify vendor/product match your Coral device with `lsusb` and adjust accordingly.
3. Restart udev: sudo udevadm control --reload && sudo udevadm trigger
4. Verify the device is visible: lsusb and check /dev/bus/usb
5. The frigate.container template mounts /dev/bus/usb; ensure Podman has permission to access the device.

Using the scaffold script
-------------------------

1. Create and activate a Python venv in the repo root:
   uv venv
2. Install requirements:
   uv pip install -r requirements.txt
3. Run the scaffold generator (reads scripts/apps.yaml):
   uv run python3 scripts/scaffold-homelab-batch.py <manifest.yaml>

This script will generate .container quadlets under .config/containers/systemd/ and Caddy site fragments based on the manifest.

Generating FCOS Ignition
------------------------

Once .config/containers/systemd/ and homelab/ files are in place, use the provided generator:
   ./system/generateIgnition.sh
This produces fcos.ign using butane in a container. Flash the ignition to the FCOS target according to your provisioning workflow.

Deployment checklist
--------------------

- [ ] All container configs are described in one or more YAML manifests like `scripts/apps.yaml`
- [ ] Run scaffold script inside venv to create quadlets and caddy fragments
- [ ] Review and populate homelab/frigate/frigate.env on the host with secrets (do not commit them)
- [ ] Generate fcos.ign and provision System A
- [ ] Boot System B, enable VLAN 30 interface and confirm Coral device visible
- [ ] systemctl enable --now frigate.container (or podman play kube / systemd enable)
- [ ] Validate: Caddy only one reachable on DMZ
- [ ] Frigate camera streams working; Coral hardware acceleration detected

Notes
-----

- Domain and certificates are handled by Caddy via existing templates in the repo; reuse those files when running scaffold.
- For any generated files that require secret values (MQTT passwords, camera credentials, service credentials), store them on the host in `homelab/<container>/<container>.env.example` and do not commit secrets.
- The Frigate container will need a shm_size of 1000mb.
