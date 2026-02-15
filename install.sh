#!/bin/bash
set -euo pipefail

TOOLKIT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="${TOOLKIT_DIR}/.venv"
BIN_DIR="${TOOLKIT_DIR}/bin"
PHONEINFOGA_VERSION="v2.11.0"

echo "=== Privacy Toolkit Installer ==="
echo ""

# Step 1: Create Python virtual environment
echo "[1/5] Creating Python virtual environment..."
python3 -m venv "${VENV_DIR}"
source "${VENV_DIR}/bin/activate"

# Step 2: Install Python dependencies
echo "[2/5] Installing Python dependencies..."
pip install --upgrade pip --quiet
pip install -r "${TOOLKIT_DIR}/requirements.txt" --quiet
echo "  Python packages installed."

# Step 3: Install Playwright Chromium (headless shell only)
echo "[3/5] Installing Playwright Chromium..."
playwright install chromium 2>/dev/null || echo "  Note: Run 'playwright install chromium' manually if this failed."

# Step 4: Download PhoneInfoga binary
echo "[4/5] Downloading PhoneInfoga ${PHONEINFOGA_VERSION}..."
if [ ! -f "${BIN_DIR}/phoneinfoga" ]; then
    curl -sSL "https://github.com/sundowndev/phoneinfoga/releases/download/${PHONEINFOGA_VERSION}/phoneinfoga_Linux_x86_64.tar.gz" \
        | tar -xz -C "${BIN_DIR}" phoneinfoga 2>/dev/null || echo "  Note: PhoneInfoga download failed. Download manually."
    [ -f "${BIN_DIR}/phoneinfoga" ] && chmod +x "${BIN_DIR}/phoneinfoga"
else
    echo "  PhoneInfoga already present."
fi

# Step 5: Pull SpiderFoot Docker image (optional)
echo "[5/5] Pulling SpiderFoot Docker image..."
docker pull ghcr.io/smicallef/spiderfoot:latest 2>/dev/null || echo "  Note: SpiderFoot Docker pull failed. Run 'docker pull ghcr.io/smicallef/spiderfoot:latest' manually."

# Create CLI entry point
cat > "${TOOLKIT_DIR}/privacy-toolkit" << 'ENTRY'
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="${SCRIPT_DIR}"
exec "${SCRIPT_DIR}/.venv/bin/python" -m src.cli "$@"
ENTRY
chmod +x "${TOOLKIT_DIR}/privacy-toolkit"

# Create convenience symlink
mkdir -p "${HOME}/.local/bin"
ln -sf "${TOOLKIT_DIR}/privacy-toolkit" "${HOME}/.local/bin/privacy-toolkit"

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Usage: privacy-toolkit --help"
echo ""
echo "Next steps:"
echo "  1. Create a profile:  privacy-toolkit profile create <name>"
echo "  2. Configure SMTP:    Edit config/config.yaml"
echo "  3. Run first scan:    privacy-toolkit scan full -p <name>"
