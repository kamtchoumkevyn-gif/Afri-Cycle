#!/usr/bin/env bash
# Sets up, or updates, Africycle on a free PythonAnywhere account.
#
# Before the first run, create the web app: Web tab -> Add a new web app ->
# Manual configuration -> Python 3.13.
#
# First time, in a PythonAnywhere Bash console (put your admin phone number last):
#   git clone https://github.com/kamtchoumkevyn-gif/Afri-Cycle.git && bash Afri-Cycle/africycle/deploy/pythonanywhere.sh 6XXXXXXXX
# To update after changes reach GitHub:
#   bash ~/Afri-Cycle/africycle/deploy/pythonanywhere.sh
# Then press Reload on the Web tab.
set -euo pipefail

main() {
    local admin_numbers="${1:-}"
    local project repo backend venv env_file wsgi site_packages domain
    project="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    repo="$(dirname "$project")"
    backend="$project/backend"
    venv="$HOME/.virtualenvs/africycle"
    env_file="$project/.env"

    echo "==> Getting the latest code"
    git -C "$repo" pull --ff-only

    echo "==> Installing Python packages (this can take a couple of minutes)"
    [ -x "$venv/bin/python" ] || python3.13 -m venv "$venv"
    "$venv/bin/pip" install --quiet --disable-pip-version-check -r "$backend/requirements.txt"

    echo "==> Writing settings to .env"
    touch "$env_file"
    chmod 600 "$env_file"
    if ! grep -q '^JWT_SECRET_KEY=.' "$env_file"; then
        { grep -v '^JWT_SECRET_KEY=' "$env_file" || true; } > "$env_file.tmp"
        echo "JWT_SECRET_KEY=$("$venv/bin/python" -c 'import secrets; print(secrets.token_hex(32))')" >> "$env_file.tmp"
        mv "$env_file.tmp" "$env_file"
    fi
    if [ -n "$admin_numbers" ]; then
        { grep -v '^ADMIN_PHONE_NUMBERS=' "$env_file" || true; } > "$env_file.tmp"
        echo "ADMIN_PHONE_NUMBERS=$admin_numbers" >> "$env_file.tmp"
        mv "$env_file.tmp" "$env_file"
    elif ! grep -q '^ADMIN_PHONE_NUMBERS=.' "$env_file"; then
        echo "Put your admin phone number at the end of the command, e.g. ... pythonanywhere.sh 6XXXXXXXX" >&2
        exit 1
    fi
    chmod 600 "$env_file"

    echo "==> Checking that the app starts"
    (cd "$backend" && "$venv/bin/python" -c "import app")

    echo "==> Connecting the web app"
    wsgi="$(ls /var/www/*_wsgi.py 2>/dev/null | head -n 1 || true)"
    if [ -z "$wsgi" ]; then
        echo "No web app found. On the Web tab: Add a new web app -> Manual configuration -> Python 3.13." >&2
        echo "Then run this command again." >&2
        exit 1
    fi
    site_packages="$("$venv/bin/python" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
    cat > "$wsgi" <<EOF
# Written by africycle/deploy/pythonanywhere.sh. Run that script again instead of editing this.
import site
import sys

# Use the africycle virtualenv's packages ahead of the system ones
before = list(sys.path)
site.addsitedir("$site_packages")
sys.path[:] = [p for p in sys.path if p not in before] + before
sys.path.insert(0, "$backend")

from app import app as application
EOF

    domain="$(basename "$wsgi" _wsgi.py | tr '_' '.')"
    echo
    echo "Done. Press the green Reload button on the Web tab, then open https://$domain"
}

main "$@"
