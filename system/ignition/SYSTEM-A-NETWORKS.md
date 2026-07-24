System A: Multi-Network Quadlet Setup
======================================

Overview
--------
System A (FCOS + Podman) has 4 ethernet ports wired to separate physical networks:
- ens1 → DMZ (internet-facing, Caddy + other public services)
- ens2 → IOT (IoT devices, Home Assistant, MQTT, Zigbee)
- ens3 → NOT (internal infrastructure, do not expose)
- ens4 → SERVER (internal services, databases, backups)

All interfaces use DHCP (IPv4 only). FCOS uses systemd predictable interface naming (enp*s* or ens*).

Network Architecture
--------------------

Podman networks are defined via .network quadlet files (similar to .container files).

For System A, create four networks:
- dmz-net:    bridge network for internet-facing services
- iot-net:    bridge network for IoT devices, Home Assistant, MQTT
- not-net:    bridge network for internal infrastructure
- server-net: bridge network for databases, backups, backend services

Containers reference networks by name in their quadlet files.

Service Dependencies & Networking
----------------------------------

Key considerations:

1. Cross-network dependencies:
   - Caddy (dmz-net) needs to reverse-proxy services on other networks.
   - Solution: Run Caddy with Network=host OR attach it to multiple networks (advanced).

2. Backend dependencies:
   - Authentik (iot-net) depends on postgres (server-net).
   - Solution: Use Network=server-net for both, or use `requires:` and network routing.
   - For tighter isolation: run postgres on server-net, but allow iot-net containers to reach postgres via firewall rules.

3. Multi-NIC services (less common):
   - If a service needs access to multiple networks, either run it with Network=host or attach multiple networks.

Quadlet Files Structure
-----------------------

Podman network quadlets (.network files) go in .config/containers/systemd/.

Example: .config/containers/systemd/dmz-net.network

   [Network]
   Description=DMZ network (internet-facing)

Example: .config/containers/systemd/iot-net.network

   [Network]
   Description=IOT network (devices, home automation)

Example: Container attachment

   # In a container quadlet:
   Network=dmz-net

   # Or multiple networks (requires quadlet_extra or manual)

Deployment Sequence
-------------------

1. Create .network quadlet files in .config/containers/systemd/ for each network.
   - Can be done manually or via a helper script.

2. Update scripts/apps.yaml to specify network for each app:
   - caddy, auth (if exposed): dmz-net
   - homeassistant, mqtt, zigbee: iot-net
   - postgres, auth (backend): server-net
   - other infrastructure: not-net

3. Regenerate quadlets via scaffold:
   uv run python3 scripts/scaffold-homelab-batch.py --manifest scripts/apps.yaml --force

4. Update fcos.bu to include:
   - Copying .config/containers/systemd/*.network files to /home/core/.config/containers/systemd/
   - (Already configured: .config/containers/systemd tree is copied by fcos.bu)

5. Generate Ignition:
   ./system/generateIgnition.sh

6. Provision System A, boot, and verify:
   - Check `podman network ls`
   - Verify containers are on correct networks: `podman inspect <container> | grep -A 5 Networks`
   - Test cross-network connectivity if needed (e.g., Caddy → backend services)

Example: apps.yaml entries for System A
----------------------------------------

Caddy (DMZ):
   - name: caddy
     image: localhost/caddy-custom:latest
     network: dmz-net
     ports:
       - 8080:80
       - 8443:443

Authentik (IOT, depends on postgres):
   - name: auth
     image: ghcr.io/goauthentik/server:latest
     network: iot-net
     ports:
       - 9000:9000
     requires:
       - postgres

PostgreSQL (SERVER):
   - name: postgres
     image: docker.io/library/postgres:16-alpine
     network: server-net
     ports:
       - 5432:5432

Home Assistant (IOT):
   - name: homeassistant
     image: ghcr.io/home-assistant/home-assistant:stable
     network: host  # ← HA needs host for device discovery
     ports:
       - 8123

MQTT (IOT):
   - name: mqtt
     image: docker.io/eclipse-mosquitto:latest
     network: iot-net
     ports:
       - 1883:1883

Cross-Network Communication (if needed)
----------------------------------------

If a service on one network needs to reach another (e.g., Caddy on dmz-net reaching MQTT on iot-net):

Option 1: Use Network=host for Caddy (simpler but less isolated).
Option 2: Attach Caddy to both networks via quadlet_extra:
   quadlet_extra:
     - Network=iot-net

Option 3: Use firewall rules on the host to allow inter-network traffic.

Troubleshooting
---------------

- **Container can't reach external network**: Check DHCP on the physical interface (nmcli device show ens1).
- **Containers can't reach each other across networks**: Verify both are on correct networks, or enable routing between networks.
- **Port conflicts**: Ensure PublishPort mappings don't conflict; use unique port numbers per container.

References
----------
- Podman networking: https://docs.podman.io/en/latest/markdown/podman-network.1.html
- FCOS predictable interface naming: https://docs.fedoraproject.org/en-US/fedora-coreos/
- Systemd Quadlets: https://docs.podman.io/en/latest/markdown/podman-systemd.unit.5.html

Next Steps
----------
1. Create .network quadlet files for dmz-net, iot-net, not-net, server-net.
2. Update scripts/apps.yaml with network assignments.
3. Run scaffold to generate container quadlets.
4. Update fcos.bu with network creation service (optional; networks can be auto-created on first podman use).
5. Generate Ignition and test on System A hardware.
