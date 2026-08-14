#!/usr/bin/env python3
"""
OSM edit CLI tool for updating way tags via OAuth 2.0
Part of the Wheels4Wheels project
"""

import os
import sys
import json
import argparse
import threading
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib.parse import urlencode, parse_qs, urlparse

import requests
from requests_oauthlib import OAuth2Session
from dotenv import load_dotenv
from lxml import etree

import sys
sys.path.insert(0, str(Path(__file__).parent))
from osm_utils import find_way_by_coordinates, check_existing_smoothness


PROJECT_ROOT = Path(__file__).parent.parent.parent
TOKEN_FILE = PROJECT_ROOT / '.osm_token.json'

# shared session with user-agent (Varnish CDN blocks requests without one)
_session = requests.Session()
_session.headers['User-Agent'] = 'W4W-CLI/0.1'


def load_env_config() -> Dict[str, str]:
    """load environment configuration from .env file"""
    env_path = PROJECT_ROOT / '.env'
    if not env_path.exists():
        print(f"Error: .env file not found at {env_path}")
        print("Please create .env file. See .env.example for template.")
        sys.exit(1)

    load_dotenv(env_path)

    required_vars = [
        'OSM_CLIENT_ID',
        'OSM_CLIENT_SECRET',
        'OSM_REDIRECT_URI',
        'OSM_BASE_URL',
        'OSM_OAUTH_AUTHORIZE_URL',
        'OSM_OAUTH_TOKEN_URL'
    ]

    config = {}
    for var in required_vars:
        value = os.getenv(var)
        if not value:
            print(f"Error: {var} not set in .env file")
            sys.exit(1)
        config[var] = value

    config['OSM_SCOPES'] = os.getenv('OSM_SCOPES', 'write_api')

    return config


def save_token(token: Dict) -> None:
    """save OAuth token to file"""
    with open(TOKEN_FILE, 'w') as f:
        json.dump(token, f, indent=2)
    print(f"Token saved to {TOKEN_FILE}")


def load_token() -> Optional[Dict]:
    """load OAuth token from file"""
    if not TOKEN_FILE.exists():
        return None

    try:
        with open(TOKEN_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    """temporary handler to capture OAuth callback"""
    auth_code = None

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        if 'code' in params:
            _OAuthCallbackHandler.auth_code = params['code'][0]
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(b'<html><body><h2>Authorization successful.</h2>'
                             b'<p>You can close this tab and return to the terminal.</p>'
                             b'</body></html>')
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'No authorization code received.')

    def log_message(self, format, *args):
        pass  # suppress request logs


def login_flow(config: Dict) -> None:
    """execute OAuth 2.0 login flow with localhost callback"""
    client_id = config['OSM_CLIENT_ID']
    redirect_uri = config['OSM_REDIRECT_URI']
    scopes = config['OSM_SCOPES'].split()

    oauth = OAuth2Session(
        client_id,
        redirect_uri=redirect_uri,
        scope=scopes
    )

    authorization_url, state = oauth.authorization_url(
        config['OSM_OAUTH_AUTHORIZE_URL']
    )

    is_localhost = redirect_uri.startswith('http://127.0.0.1')

    if is_localhost:
        # parse port from redirect URI
        parsed_redirect = urlparse(redirect_uri)
        port = parsed_redirect.port or 8765

        # start temporary server
        _OAuthCallbackHandler.auth_code = None
        server = HTTPServer(('127.0.0.1', port), _OAuthCallbackHandler)
        server.timeout = 120

        print("Opening browser for OSM authorization...")
        webbrowser.open(authorization_url)
        print(f"Waiting for callback on port {port}... (timeout: 120s)")

        # serve until we get the code or timeout
        while _OAuthCallbackHandler.auth_code is None:
            server.handle_request()

        server.server_close()
        code = _OAuthCallbackHandler.auth_code

        if not code:
            print("Error: No authorization code received")
            sys.exit(1)
    else:
        # fallback: manual paste flow (OOB or custom redirect)
        print("=" * 70)
        print("Open this URL in your browser:")
        print(f"\n{authorization_url}\n")
        print("After authorizing, paste the code or redirect URL below.")
        print("=" * 70)

        user_input = input("\nPaste here: ").strip()

        if user_input.startswith('http://') or user_input.startswith('https://'):
            parsed = urlparse(user_input)
            query_params = parse_qs(parsed.query)
            if 'code' not in query_params:
                print("Error: No 'code' parameter found in URL")
                sys.exit(1)
            code = query_params['code'][0]
        else:
            code = user_input

        if not code:
            print("Error: No authorization code provided")
            sys.exit(1)

    print("Exchanging code for access token...")

    token_data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': redirect_uri,
        'client_id': config['OSM_CLIENT_ID'],
        'client_secret': config['OSM_CLIENT_SECRET']
    }

    response = _session.post(
        config['OSM_OAUTH_TOKEN_URL'],
        data=token_data,
        headers={'Content-Type': 'application/x-www-form-urlencoded'}
    )

    if response.status_code != 200:
        print(f"Error: Failed to get access token")
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
        sys.exit(1)

    token = response.json()
    save_token(token)

    print("\nSUCCESS: Authentication complete!")
    print("You can now use 'set-tag' command to edit ways.")


def get_valid_token(config: Dict) -> str:
    """get valid access token, refresh if needed"""
    token = load_token()

    if not token:
        print("Error: Not logged in. Run 'login' command first.")
        sys.exit(1)

    if 'access_token' not in token:
        print("Error: Invalid token file. Run 'login' command again.")
        sys.exit(1)

    return token['access_token']


def create_changeset(access_token: str, config: Dict, comment: str) -> str:
    """create a new changeset"""
    changeset_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<osm>
  <changeset>
    <tag k="created_by" v="W4W CLI/0.1"/>
    <tag k="comment" v="{comment}"/>
  </changeset>
</osm>'''

    url = f"{config['OSM_BASE_URL']}/api/0.6/changeset/create"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'text/xml'
    }

    response = _session.put(url, data=changeset_xml.encode('utf-8'), headers=headers)

    if response.status_code != 200:
        print(f"Error: Failed to create changeset")
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
        sys.exit(1)

    changeset_id = response.text.strip()
    print(f"Created changeset: {changeset_id}")
    return changeset_id


def get_way(way_id: str, access_token: str, config: Dict) -> etree.Element:
    """fetch current way data from OSM"""
    url = f"{config['OSM_BASE_URL']}/api/0.6/way/{way_id}"
    headers = {'Authorization': f'Bearer {access_token}'}

    response = _session.get(url, headers=headers)

    if response.status_code != 200:
        print(f"Error: Failed to fetch way {way_id}")
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
        sys.exit(1)

    return etree.fromstring(response.content)


def modify_way_tags(way_xml: etree.Element, key: str, value: str, changeset_id: str) -> etree.Element:
    """modify way tags in XML"""
    osm = way_xml
    way = osm.find('way')

    if way is None:
        print("Error: Invalid way XML structure")
        sys.exit(1)

    way.set('changeset', changeset_id)

    existing_tag = None
    for tag in way.findall('tag'):
        if tag.get('k') == key:
            existing_tag = tag
            break

    if existing_tag is not None:
        existing_tag.set('v', value)
        print(f"Updated existing tag: {key}={value}")
    else:
        new_tag = etree.Element('tag', k=key, v=value)
        way.append(new_tag)
        print(f"Added new tag: {key}={value}")

    return osm


def upload_way(way_id: str, way_xml: etree.Element, access_token: str, config: Dict) -> str:
    """upload modified way to OSM"""
    url = f"{config['OSM_BASE_URL']}/api/0.6/way/{way_id}"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'text/xml'
    }

    xml_data = etree.tostring(way_xml, encoding='utf-8', xml_declaration=True)

    response = _session.put(url, data=xml_data, headers=headers)

    if response.status_code == 409:
        print("Error: Version conflict (409). The way was modified by someone else.")
        print("You need to fetch the latest version and try again.")
        sys.exit(1)

    if response.status_code != 200:
        print(f"Error: Failed to upload way")
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
        sys.exit(1)

    new_version = response.text.strip()
    return new_version


def audit_snapshot(way: etree.Element, key: str) -> Dict:
    """return the OSM state needed to reverse one tag edit safely"""
    tag_value = None
    tag_present = False
    for tag in way.findall('tag'):
        if tag.get('k') == key:
            tag_value = tag.get('v')
            tag_present = True
            break

    return {
        'version': int(way.get('version')),
        'changeset_id': way.get('changeset'),
        'tag_present': tag_present,
        'tag_value': tag_value,
    }


def print_audit_snapshot(phase: str, snapshot: Dict) -> None:
    """emit one machine-readable line while keeping normal CLI output intact"""
    print(f"W4W_AUDIT_{phase.upper()}:" + json.dumps(snapshot, separators=(',', ':')))


def ensure_create_only_allowed(snapshot: Dict, key: str) -> None:
    """Refuse a create-only edit when the current way already has the tag."""
    if snapshot['tag_present']:
        raise ValueError(
            f"create-only refused: way already has {key}={snapshot['tag_value']!r}"
        )


def close_changeset(changeset_id: str, access_token: str, config: Dict) -> None:
    """close the changeset"""
    url = f"{config['OSM_BASE_URL']}/api/0.6/changeset/{changeset_id}/close"
    headers = {'Authorization': f'Bearer {access_token}'}

    response = _session.put(url, headers=headers)

    if response.status_code != 200:
        print(f"Warning: Failed to close changeset {changeset_id}")
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
    else:
        print(f"Closed changeset: {changeset_id}")


def set_tag_command(args: argparse.Namespace, config: Dict) -> None:
    """execute set-tag command to modify a way with confirmation logic"""
    way_id = args.way_id
    key = args.key
    value = args.value
    comment = args.comment
    auto_confirm = getattr(args, 'yes', False)
    create_only = getattr(args, 'create_only', False)

    print(f"\nPreparing to modify way {way_id}: {key}={value}")
    print(f"Changeset comment: {comment}\n")

    access_token = get_valid_token(config)

    try:
        # Fetch way first to inspect current tags before opening a changeset
        print(f"Fetching way {way_id}...")
        way_xml = get_way(way_id, access_token, config)
        way = way_xml.find('way')
        current_version = way.get('version')

        before_snapshot = audit_snapshot(way, key)
        print_audit_snapshot('before', before_snapshot)

        if create_only:
            ensure_create_only_allowed(before_snapshot, key)

        # Read current tag value if present
        current_tag_value = before_snapshot['tag_value']

        # Decide action based on current tag state
        if current_tag_value is not None:
            if current_tag_value == value:
                print(f"No change needed: {key} is already '{value}' (version {current_version}).")
                print(f"View way: https://www.openstreetmap.org/way/{way_id}")
                return
            else:
                if auto_confirm:
                    proceed = True
                else:
                    answer = input(
                        f"Override existing tag '{key}={current_tag_value}' with '{key}={value}'? [y/N]: "
                    ).strip().lower()
                    proceed = answer in ("y", "yes")
                if not proceed:
                    print("Aborted by user. No changes made.")
                    return
        else:
            if auto_confirm:
                proceed = True
            else:
                answer = input(
                    f"Tag '{key}' does not exist. Create '{key}={value}'? [Y/n]: "
                ).strip().lower()
                proceed = (answer in ("", "y", "yes"))
            if not proceed:
                print("Aborted by user. No changes made.")
                return

        # Proceed with change inside a changeset
        changeset_id = create_changeset(access_token, config, comment)
        print(f"Current version: {current_version}")

        modified_xml = modify_way_tags(way_xml, key, value, changeset_id)
        print("Uploading modified way...")
        new_version = upload_way(way_id, modified_xml, access_token, config)

        close_changeset(changeset_id, access_token, config)

        print_audit_snapshot('after', {
            'version': int(new_version),
            'changeset_id': changeset_id,
            'tag_present': True,
            'tag_value': value,
        })

        changeset_url = f"https://www.openstreetmap.org/changeset/{changeset_id}"
        way_url = f"https://www.openstreetmap.org/way/{way_id}"

        print(f"\nSUCCESS: way {way_id} v{current_version} -> v{new_version}")
        print(f"Changeset: {changeset_url}")
        print(f"Way: {way_url}")

        if getattr(args, 'open', False):
            webbrowser.open(changeset_url)

    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)


def find_way_command(args: argparse.Namespace) -> None:
    """execute find-way command to locate ways by coordinates"""
    lat = args.lat
    lon = args.lon
    radius = args.radius
    auto_confirm = args.yes

    way_id = find_way_by_coordinates(lat, lon, radius, interactive=True, auto_confirm=auto_confirm)

    if way_id:
        print(f"\n" + "=" * 70)
        print(f"Selected way ID: {way_id}")
        print("=" * 70)

        existing = check_existing_smoothness(way_id)
        if existing:
            print(f"Note: This way already has smoothness={existing}")
        else:
            print("This way does not have a smoothness tag yet.")

        print(f"\nView on OSM: https://www.openstreetmap.org/way/{way_id}")


def main():
    """main entry point"""
    parser = argparse.ArgumentParser(
        description='OSM way editor for Wheels4Wheels project',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # First time setup - authenticate
  uv run python scripts/OSM/osm_edit.py login

  # Find way by coordinates
  uv run python scripts/OSM/osm_edit.py find-way --lat 50.328132 --lon 8.738048

  # Find way and auto-select (non-interactive)
  uv run python scripts/OSM/osm_edit.py find-way --lat 50.328132 --lon 8.738048 -y

  # Set smoothness tag on a way (by way ID)
  uv run python scripts/OSM/osm_edit.py set-tag --way-id 123456 --key smoothness --value intermediate --comment "W4W: add surface smoothness data"

  # Find and set in one command (interactive)
  uv run python scripts/OSM/osm_edit.py set-tag --lat 50.328132 --lon 8.738048 --key smoothness --value intermediate --comment "W4W: add surface smoothness"

  # Find and set with auto-confirm (for batch processing)
  uv run python scripts/OSM/osm_edit.py set-tag --lat 50.328132 --lon 8.738048 --key smoothness --value intermediate --comment "W4W: add surface smoothness" -y
        '''
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    login_parser = subparsers.add_parser('login', help='Authenticate with OSM OAuth')

    find_way_parser = subparsers.add_parser('find-way', help='Find way ID from coordinates')
    find_way_parser.add_argument('--lat', type=float, required=True, help='Latitude')
    find_way_parser.add_argument('--lon', type=float, required=True, help='Longitude')
    find_way_parser.add_argument('--radius', type=int, default=20, help='Search radius in meters (default: 20)')
    find_way_parser.add_argument('-y', '--yes', action='store_true', help='Auto-confirm selection without prompting')

    set_tag_parser = subparsers.add_parser('set-tag', help='Set or update a tag on a way')
    way_group = set_tag_parser.add_mutually_exclusive_group(required=True)
    way_group.add_argument('--way-id', type=int, help='OSM way ID to modify')
    way_group.add_argument('--lat', type=float, help='Latitude (use with --lon to find way)')
    set_tag_parser.add_argument('--lon', type=float, help='Longitude (required if using --lat)')
    set_tag_parser.add_argument('--radius', type=int, default=20, help='Search radius in meters (default: 20)')
    set_tag_parser.add_argument('-y', '--yes', action='store_true', help='Auto-confirm way selection without prompting')
    set_tag_parser.add_argument('--key', required=True, help='Tag key (e.g., smoothness)')
    set_tag_parser.add_argument('--value', required=True, help='Tag value (e.g., intermediate)')
    set_tag_parser.add_argument('--comment', default='W4W: update way tags', help='Changeset comment')
    set_tag_parser.add_argument(
        '--create-only',
        action='store_true',
        help='Refuse the edit if the current way already has the target tag',
    )
    set_tag_parser.add_argument('--open', action='store_true', help='Open changeset in browser after upload')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    config = load_env_config()

    if args.command == 'login':
        login_flow(config)
    elif args.command == 'find-way':
        find_way_command(args)
    elif args.command == 'set-tag':
        if args.lat is not None:
            if args.lon is None:
                print("Error: --lon is required when using --lat")
                sys.exit(1)

            print(f"Finding way at coordinates ({args.lat}, {args.lon})...")
            auto_confirm = args.yes
            way_id = find_way_by_coordinates(args.lat, args.lon, args.radius, interactive=True, auto_confirm=auto_confirm)

            if not way_id:
                print("No way selected. Exiting.")
                sys.exit(1)

            args.way_id = way_id

        set_tag_command(args, config)


if __name__ == '__main__':
    main()
