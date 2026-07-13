#!/usr/bin/env python3
"""
Scaffold Podman homelab infrastructure from batch YAML manifest.
Generates Quadlet container definitions, Caddy reverse proxy configs, and environment templates.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, Dict, List, Any
import yaml


class ManifestParser:
    """Parse and validate homelab batch manifests from a YAML string.

    This class no longer opens files directly; callers should validate and
    read manifest files before instantiating ManifestParser. This design
    eliminates file-based path-traversal risks inside the parser.
    """

    def __init__(self, manifest_text: str):
        try:
            data = yaml.safe_load(manifest_text)
            self.data = data or {}
        except Exception as e:
            raise RuntimeError(f"Failed to parse manifest content: {e}")
    
    def get_defaults(self) -> Dict[str, Any]:
        """Extract global defaults from manifest."""
        return self.data.get('defaults', {})

    def get_apps(self) -> List[Dict[str, Any]]:
        """Extract and normalize apps from manifest."""
        apps_raw = self.data.get('apps', [])
        if not apps_raw:
            return []
        
        defaults = self.get_defaults()
        apps = []
        for app_data in apps_raw:
            app = self._normalize_app(app_data, defaults)
            if app:
                apps.append(app)
        
        return apps
    
    def _normalize_auth(self, value: Any) -> str:
        """Normalize auth values from YAML/CLI input to the expected strings."""
        if isinstance(value, bool):
            return 'yes' if value else 'no'

        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in ('yes', 'true', 'on', '1'):
                return 'yes'
            if normalized in ('no', 'false', 'off', '0'):
                return 'no'
            if normalized in ('auto', ''):
                return 'auto'

        return str(value).strip().lower() if value is not None else 'auto'

    def _normalize_list_field(self, value: Any) -> List[str]:
        """Normalize a manifest field that may be a single string or a list."""
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value if item is not None]
        if isinstance(value, tuple):
            return [str(item) for item in value if item is not None]
        if isinstance(value, str):
            stripped = value.strip()
            return [stripped] if stripped else []
        return [str(value)]

    def _normalize_app(self, app_data: Dict[str, Any], defaults: Dict[str, Any] = {}) -> Optional[Dict[str, Any]]:
        """Normalize and validate app data."""
        if not isinstance(app_data, dict):
            return None
        
        # Required fields
        name = app_data.get('name', '').strip()
        image = app_data.get('image', '').strip()
        
        if not name or not image:
            return None
        
        # Parse ports field: list of port numbers or host:container mappings
        ports_raw = app_data.get('ports', []) or []
        container_port = self._extract_container_port(ports_raw)
        publish_mappings = self._extract_publish_mappings(ports_raw)
        
        # Optional fields with defaults
        return {
            'name': name,
            'image': image,
            'port': container_port,
            'subdomain': app_data.get('subdomain', name),
            'domain': app_data.get('domain', 'mydomain.tld'),
            'exposure': app_data.get('exposure', 'local'),
            'auth': self._normalize_auth(app_data.get('auth', 'auto')),
            'network': app_data.get('network', 'bridge'),
            'userns': app_data.get('userns', defaults.get('userns', 'keep-id')),
            'selinux_label': app_data.get('selinux_label') or app_data.get('selinux-label', 'Z'),
            'publish': publish_mappings,
            'requires': app_data.get('requires', []) or [],
            'volumes': app_data.get('volumes', []) or [],
            'devices': app_data.get('devices', []) or [],
            'podman_args': self._normalize_list_field(
                app_data.get('podman_args', app_data.get('extra_args', defaults.get('podman_args', defaults.get('extra_args', []))))
            ),
            'container_args': self._normalize_list_field(app_data.get('container_args', defaults.get('container_args', []))),
            'quadlet_extra': self._normalize_list_field(app_data.get('quadlet_extra', defaults.get('quadlet_extra', []))),
            'timezone': app_data.get('timezone') or defaults.get('timezone', 'UTC'),
            'update': app_data.get('update') or defaults.get('update', 'registry'),
        }
    
    def _extract_container_port(self, ports: List[Any]) -> int:
        """Extract the primary container port from ports list."""
        if not ports:
            return 8080
        
        # For "host:container" format, use the container port (right side)
        # For bare numbers, use that port
        first_port = str(ports[0])
        if ':' in first_port:
            # Extract right side of mapping (container port)
            parts = first_port.split(':')
            return int(parts[1].split('/')[0])  # Strip /protocol if present
        else:
            # Bare port number
            return int(first_port.split('/')[0])
    
    def _extract_publish_mappings(self, ports: List[Any]) -> List[str]:
        """Extract publish mappings from ports list."""
        if not ports:
            return []
        
        mappings = []
        for port_spec in ports:
            port_str = str(port_spec)
            if ':' in port_str:
                # Already a mapping, use as-is
                mappings.append(port_str)
            # else: bare port number, no publish mapping
        
        return mappings


class AppScaffolder:
    """Generate infrastructure files for an app."""
    
    def __init__(self, app: Dict[str, Any], workspace_root: Path, dry_run: bool = False):
        self.app = app
        self.workspace_root = workspace_root
        self.dry_run = dry_run
    
    def scaffold(self) -> Dict[str, Any]:
        """Generate all infrastructure files for this app."""
        result = {
            'status': 'ok',
            'app': self.app['name'],
            'image': self.app['image'],
        }
        
        try:
            self._generate_container_file()
            self._generate_caddy_config()
            self._generate_env_template()
            
            result['container_file'] = str(self._get_container_path())
            result['caddy_file'] = str(self._get_caddy_path())
            result['env_file'] = str(self._get_env_path())
        except Exception as e:
            result['status'] = 'error'
            result['error'] = str(e)
        
        return result
    
    def _get_container_path(self) -> Path:
        """Get path for Quadlet .container file."""
        return self.workspace_root / '.config' / 'containers' / 'systemd' / f"{self.app['name']}.container"
    
    def _get_caddy_path(self) -> Path:
        """Get path for Caddy site config."""
        return self.workspace_root / 'homelab' / 'caddy' / 'sites' / f"{self.app['name']}.caddy"
    
    def _get_env_path(self) -> Path:
        """Get path for environment template."""
        app_dir = self.workspace_root / 'homelab' / self.app['name']
        return app_dir / f"{self.app['name']}.env.example"

    def _get_env_file_path(self) -> Path:
        """Get path for the runtime environment file used by the container."""
        app_dir = self.workspace_root / 'homelab' / self.app['name']
        return app_dir / f"{self.app['name']}.env"
    
    def _ensure_volume_directories(self, volumes: List[str]):
        """Create host-side directories for relative volume mounts."""
        for volume_spec in volumes:
            if not isinstance(volume_spec, str) or not volume_spec.strip():
                continue

            parts = volume_spec.split(':')
            if len(parts) < 2:
                continue

            host_path = parts[0].strip()
            if not host_path:
                continue

            host_path_obj = Path(host_path).expanduser()
            if not host_path_obj.is_absolute():
                # Treat POSIX-style absolute paths (starting with '/') as external
                # and do not attempt to create them when generating on non-Linux
                # hosts. For relative paths, resolve them under the workspace and
                # prevent traversal outside the workspace. For absolute paths with
                # a drive (Windows) or valid absolute paths on Linux, allow mkdir.
                host_path_str = host_path
                if host_path_str.startswith('/') and os.name == 'nt':
                    # Running on Windows and manifest references a POSIX absolute
                    # path (e.g. /run/dbus). Do not create it; leave as-is.
                    continue

                if not host_path_obj.is_absolute():
                    # Resolve relative host paths under workspace_root and prevent
                    # path traversal (../../) escaping the workspace.
                    candidate = (self.workspace_root / host_path_obj)
                    resolved = candidate.resolve()
                    workspace_resolved = self.workspace_root.resolve()
                    if not (str(resolved) == str(workspace_resolved) or str(resolved).startswith(str(workspace_resolved) + os.sep)):
                        raise RuntimeError(f"Refusing to create volume directory outside workspace: {host_path}")
                    host_path_obj = resolved
                    host_path_obj.mkdir(parents=True, exist_ok=True)
                    if not any(host_path_obj.iterdir()):
                        (host_path_obj / '.gitkeep').touch(exist_ok=True)
                else:
                    # Absolute path on this OS — attempt to create (e.g., C:\path) or
                    # resolve and create on Linux hosts.
                    try:
                        host_path_obj = host_path_obj.resolve()
                        host_path_obj.mkdir(parents=True, exist_ok=True)
                        if not any(host_path_obj.iterdir()):
                            (host_path_obj / '.gitkeep').touch(exist_ok=True)
                    except Exception:
                        # If creation fails (permissions, non-existent mountpoint),
                        # skip creating but continue — container definition can still
                        # reference the host path.
                        pass

    def _generate_container_file(self):
        """Generate Quadlet container definition."""
        port = self.app.get('port') or 8080
        network = self.app.get('network', 'bridge')
        
        # Build service dependencies
        requires = self.app.get('requires', [])
        after_services = ' '.join(f"{svc}.service" for svc in requires) if requires else "network-online.target"
        wants_services = ' '.join(f"{svc}.service" for svc in requires) if requires else "network-online.target"
        
        # Ensure we always have network-online
        if not requires:
            after_services = "network-online.target"
            wants_services = "network-online.target"
        else:
            after_services += " network-online.target"
            wants_services += " network-online.target"
        
        # Build volume mounts
        volumes = []
        if self.app.get('volumes'):
            volumes = self.app['volumes']
        else:
            # Fallback default volume
            volumes = [f"homelab/{self.app['name']}:/data:Z"]
        
        volume_lines = '\n'.join(f"Volume={v}" for v in volumes)

        # Timezone
        tz = self.app.get('timezone', 'UTC')
        
        # Build device mappings
        devices = self.app.get('devices', [])
        device_lines = ''
        if devices:
            device_lines = '\n' + '\n'.join(f"Device={d}" for d in devices)
        
        # Build publish mappings (not needed for host network)
        publish_lines = ''
        if network != 'host' and self.app.get('publish'):
            publish_lines = '\n'.join(
                f"PublishPort={pub}" for pub in self.app['publish']
            )
            if publish_lines:
                publish_lines = '\n' + publish_lines

        # User namespace handling: allow 'keep-id' (map container UID to the calling user)
        userns = self.app.get('userns')
        userns_line = f"\nUserns={userns}" if userns else ''

        podman_args = self.app.get('podman_args', []) or []
        podman_arg_lines = ''
        if podman_args:
            podman_arg_lines = '\n' + '\n'.join(f"PodmanArgs={arg}" for arg in podman_args)

        container_args = self.app.get('container_args', []) or []
        container_arg_lines = ''
        if container_args:
            container_arg_lines = '\n' + '\n'.join(f"ContainerArg={arg}" for arg in container_args)

        quadlet_extra = self.app.get('quadlet_extra', []) or []
        quadlet_extra_lines = ''
        if quadlet_extra:
            quadlet_extra_lines = '\n' + '\n'.join(quadlet_extra)

        env_file_rel = self._get_env_file_path().relative_to(self.workspace_root).as_posix()

        content = f"""# Podman Quadlet container for {self.app['name']}
# Generated by scaffold-homelab-batch.py

[Unit]
Description={self.app['name']} container
After={after_services}
Wants={wants_services}

[Container]
ContainerName={self.app['name']}
Image={self.app['image']}
Network={network}{publish_lines}{userns_line}{podman_arg_lines}{container_arg_lines}{quadlet_extra_lines}

EnvironmentFile={env_file_rel}
Environment=TZ={tz}

WorkingDirectory=~
{volume_lines}{device_lines}

AutoUpdate={self.app.get('update', 'registry')}

Restart=always

[Install]
WantedBy=default.target
"""
        
        if not self.dry_run:
            self._ensure_volume_directories(volumes)
            container_path = self._get_container_path()
            container_path.parent.mkdir(parents=True, exist_ok=True)
            container_path.write_text(content)
    
    def _generate_caddy_config(self):
        """Generate Caddy reverse proxy configuration from template."""
        subdomain = self.app.get('subdomain', self.app['name'])
        domain = self.app.get('domain', 'mydomain.tld')
        exposure = self.app.get('exposure', 'local')
        port = self.app.get('port', 8080)
        auth = self.app.get('auth', 'auto')
        network = self.app.get('network', 'bridge')

        # Upstream: container name on bridge network, localhost on host network
        if network == 'host':
            upstream = f"localhost:{port}"
        else:
            upstream = f"{self.app['name']}:{port}"

        fqdn = f"{subdomain}.{domain}"

        # Select template based on exposure + auth
        use_auth = auth in ('yes', 'auto')
        if exposure == 'public':
            template_name = 'site.public_authentik.caddy.template' if use_auth else 'site.public.caddy.template'
        else:
            template_name = 'site.local_authentik.caddy.template' if use_auth else 'site.local.caddy.template'

        template_path = self.workspace_root / 'scripts' / 'templates' / 'caddy' / template_name
        template = template_path.read_text()

        content = (
            f"# Caddy reverse proxy for {self.app['name']}\n"
            f"# Generated by scaffold-homelab-batch.py\n\n"
            + template.replace('{{FQDN}}', fqdn).replace('{{UPSTREAM}}', upstream)
        )

        if not self.dry_run:
            caddy_path = self._get_caddy_path()
            caddy_path.parent.mkdir(parents=True, exist_ok=True)
            caddy_path.write_text(content)
    
    def _generate_env_template(self):
        """Create an example env template only when it does not already exist."""
        content = f"""# Environment variables for {self.app['name']}
# Generated by scaffold-homelab-batch.py
# Replace the placeholder values before starting the container.

# Example environment variables - add as needed for your app
# APP_VAR_NAME=value
"""
        
        if not self.dry_run:
            env_path = self._get_env_path()
            env_path.parent.mkdir(parents=True, exist_ok=True)
            if not env_path.exists():
                env_path.write_text(content)


def main():
    parser = argparse.ArgumentParser(
        description='Scaffold Podman homelab infrastructure from batch YAML manifest'
    )
    parser.add_argument(
        '--manifest',
        type=Path,
        required=True,
        help='Path to batch manifest YAML file'
    )
    parser.add_argument(
        '--workspace',
        type=Path,
        default=Path.cwd(),
        help='Workspace root directory (default: current directory)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be generated without creating files'
    )
    parser.add_argument(
        '--output-format',
        choices=['text', 'json'],
        default='text',
        help='Output format'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Overwrite existing files'
    )
    
    args = parser.parse_args()
    
    # Validate manifest exists
    # Resolve workspace and manifest paths
    workspace_root = args.workspace.resolve()
    manifest_path = args.manifest.resolve()

    # Ensure manifest exists
    if not manifest_path.exists():
        print(f"Error: Manifest not found: {args.manifest}", file=sys.stderr)
        sys.exit(1)

    # Security: only allow manifests that live inside the workspace root to avoid
    # accidental path traversal / arbitrary file reads. If you need to load a
    # manifest outside the workspace, copy it into the workspace or run the
    # script with --workspace pointing to its parent directory.
    try:
        manifest_path.relative_to(workspace_root)
    except Exception:
        print(f"Error: Manifest {args.manifest} is outside workspace {args.workspace}", file=sys.stderr)
        sys.exit(1)
    
    # Parse manifest
    try:
        manifest_text = manifest_path.read_text()
        parser_obj = ManifestParser(manifest_text)
        apps = parser_obj.get_apps()
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    
    if not apps:
        print(f"Error: No valid apps found in manifest: {args.manifest}", file=sys.stderr)
        sys.exit(1)
    
    # Scaffold each app
    results = []
    for app in apps:
        scaffolder = AppScaffolder(app, args.workspace, dry_run=args.dry_run)
        result = scaffolder.scaffold()
        results.append(result)
    
    # Output results
    if args.output_format == 'json':
        print(json.dumps({
            'manifest': str(args.manifest),
            'apps': results,
            'dry_run': args.dry_run,
        }, indent=2))
    else:
        total = len(results)
        successful = sum(1 for r in results if r['status'] == 'ok')
        
        for i, result in enumerate(results, 1):
            print(f"\n[{i}/{total}] {result['app']}: {result['status']}")
            if result['status'] == 'ok':
                print(f"  Container: {result.get('container_file', 'N/A')}")
                print(f"  Caddy:     {result.get('caddy_file', 'N/A')}")
                print(f"  Env:       {result.get('env_file', 'N/A')}")
            else:
                print(f"  Error: {result.get('error', 'Unknown error')}")
        
        mode = "validated" if args.dry_run else "generated"
        print(f"\n{successful}/{total} apps {mode} successfully")
        
        if successful < total:
            sys.exit(1)


if __name__ == '__main__':
    main()
