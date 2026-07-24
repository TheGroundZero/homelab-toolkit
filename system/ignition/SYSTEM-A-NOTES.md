System A (FCOS) networking and Ignition notes
===============================================

- NIC wiring: System A's 4 ethernet ports are wired at the switch to four separate physical networks: DMZ, IOT, NOT, SERVER. The switch provides VLAN or port-isolation as configured outside the host.
- DHCP: All interfaces should obtain IPv4 addresses via DHCP. Ignition/Butane will not configure static IPs; instead, ensure NetworkManager is allowed to manage interfaces and obtain DHCP leases.
- Quadlets: Container unit files placed under /home/core/.config/containers/systemd/ will be included by fcos.bu (see system/fcos.bu) and made available after first boot. Use scaffold-homelab-batch.py to generate the .container files prior to ignition creation.
- Caddy exposure: The Caddy container must be attached only to the DMZ-facing network. Use the generated .container unit's Network or Podman args to ensure it binds to the intended network namespace. On FCOS, most users rely on separate macvlan or dedicated network names to achieve per-interface containment.

Recommended minimal Ignition action items:
- Include .config/containers/systemd/ (already configured in system/fcos.bu) and homelab/ tree so quadlets and configs are present on first boot.
- Do not hardcode IPs. Validate DHCP and DNS once provisioned.
