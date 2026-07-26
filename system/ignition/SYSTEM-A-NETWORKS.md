System A: Multi-Network Quadlet Setup
======================================

Overview
--------

System A (FCOS + Podman) has 4 ethernet ports wired to separate physical networks:

- ens1 → DMZ (internet-facing, Caddy)
- ens2 → IOT (IoT devices)
- ens3 → NOT (IoT devices without internet connectivity)
- ens4 → Untagged

All interfaces use DHCP (IPv4 only). FCOS uses systemd predictable interface naming (enp*s* or ens*).

Inter-container networking happens via a virtual `homelab.network`.
Only Home Assistant and ESPHome connect to the host network.
Caddy is the only system connected to the DMZ network directly. Caddy proxies via the homelab.network or host network to the other containers.

Network Architecture
--------------------

Podman networks are defined via .network quadlet files (similar to .container files).

For System A, create four networks:

- dmz-net:    bridge network for internet-facing services (Caddy)
- iot-net:    bridge network for IoT devices
- not-net:    bridge network for NoT devices
- homelab:    virtual network for the containers

Containers reference networks by name in their quadlet files.

Service Dependencies & Networking
----------------------------------

Key considerations:

1. Cross-network dependencies:
   - Caddy (dmz-net) needs to reverse-proxy services on other networks.
   - Solution: Attach it to multiple networks.

2. Backend dependencies:
   - Authentik depends on postgres.
   - Solution: Use `Network=homelab` and `Requires:`

3. Multi-NIC services (less common):
   - If a service needs access to multiple networks, either run it with Network=host or attach multiple networks (preferred).

Quadlet Files Structure
-----------------------

Podman network quadlets (`.network` files) go in `.config/containers/systemd/`.

Example: .config/containers/systemd/dmz-net.network

   [Network]
   Description=DMZ network (internet-facing)

Example: .config/containers/systemd/iot-net.network

   [Network]
   Description=IOT network (devices, home automation)

Example: Container attachment

```ini
# In a container quadlet:
Network=dmz-net
```

```ini
# Or multiple networks (requires quadlet_extra or manual)
quadlet_extra:
- Network=iot.network
```

Deployment Sequence
-------------------

1. Create `.network` quadlet files in `.config/containers/systemd/` for each network.
   - Can be done manually or via a helper script.

2. Update `scripts/apps.yaml` to specify network for each app:
   - caddy: dmz-net, homelab, able to proxy homeassistant and esphome
   - homeassistant: host network, not and iot vlan
   - esphome: host network, not vlan
   - other containers: homelab by default

3. Regenerate quadlets via scaffold:
   `uv run python3 scripts/scaffold-homelab-batch.py --manifest scripts/apps.yaml --force`

4. Update `fcos.bu` to include:
   - Copying `.config/containers/systemd/*.network` files to `/home/core/.config/containers/systemd/`
   - (Already configured: `.config/containers/systemd` tree is copied by fcos.bu)

5. Generate Ignition:
   `./system/generateIgnition.sh`

6. Provision System A, boot, and verify:
   - Check `podman network ls`
   - Verify containers are on correct networks: `podman inspect <container> | grep -A 5 Networks`
   - Test cross-network connectivity if needed (e.g., Caddy → backend services)

Example: apps.yaml entries for System A
----------------------------------------

Caddy (DMZ):

```yaml
   - name: caddy
     image: localhost/caddy-custom:latest
     network: dmz-net
     ports:
       - 8080:80
       - 8443:443
```

Authentik (IOT, depends on postgres):

```yaml
   - name: auth
     image: ghcr.io/goauthentik/server:latest
     network: homelab
     ports:
       - 9000:9000
     requires:
       - postgres
```

PostgreSQL (SERVER):

```yaml
   - name: postgres
     image: docker.io/library/postgres:16-alpine
     network: homelab
     ports:
       - 5432:5432
```

Home Assistant (IOT):

```yaml
   - name: homeassistant
     image: ghcr.io/home-assistant/home-assistant:stable
     network: host  # ← HA needs host for device discovery
     ports:
       - 8123
```

MQTT (IOT):

```yaml
   - name: mqtt
     image: docker.io/eclipse-mosquitto:latest
     network: homelab
     ports:
       - 1883:1883
```

Troubleshooting
---------------

- **Container can't reach external network**: Check DHCP on the physical interface (`nmcli device show ens1`).
- **Containers can't reach each other across networks**: Verify both are on correct networks, or enable routing between networks.
- **Port conflicts**: Ensure PublishPort mappings don't conflict; use unique port numbers per container.

References
----------

- Podman networking: https://docs.podman.io/en/latest/markdown/podman-network.1.html
- FCOS predictable interface naming: https://docs.fedoraproject.org/en-US/fedora-coreos/
- Systemd Quadlets: https://docs.podman.io/en/latest/markdown/podman-systemd.unit.5.html

Next Steps
----------

1. Create `.network` quadlet files for dmz-net, iot-net, not-net, homelab.
2. Update `scripts/apps.yaml` with network assignments.
3. Run scaffold to generate container quadlets.
4. Update `fcos.bu` with network creation service (optional; networks can be auto-created on first podman use).
5. Generate Ignition and test on System A hardware.
