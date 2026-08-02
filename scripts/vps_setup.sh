#!/usr/bin/env bash
# vps_setup.sh — one-shot hunter stack for a Ubuntu 22.04/24.04 CPU VPS
# Works on Oracle Cloud Always Free ARM (4 OCPU/24GB) and DO/AWS/Azure x86 droplets.
# Usage:  bash vps_setup.sh
set -euo pipefail

ARCH="$(uname -m)"
if [ "$ARCH" = "aarch64" ]; then ECHIDNA_ARCH="aarch64"; else ECHIDNA_ARCH="amd64"; fi

echo "==> [1/7] System update"
sudo apt-get update -y && sudo apt-get upgrade -y

echo "==> [2/7] Ollama (ARM/x86 auto-detected)"
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl enable ollama && sudo systemctl start ollama

echo "==> [3/7] Foundry (forge, cast, anvil)"
curl -L https://foundry.paradigm.xyz | bash
export PATH="$HOME/.foundry/bin:$PATH"
grep -q 'foundry/bin' "$HOME/.bashrc" || echo 'export PATH="$HOME/.foundry/bin:$PATH"' >> "$HOME/.bashrc"
foundryup

echo "==> [4/7] solc 0.8.x (required by echidna & slither)"
pip3 install --user -q solc-select
export PATH="$HOME/.local/bin:$PATH"
solc-select install 0.8.23 && solc-select use 0.8.23

echo "==> [5/7] Slither (static analysis companion)"
pip3 install --user -q slither-analyzer

echo "==> [6/7] Echidna (differential fuzzer)"
if curl -fsSL -o /tmp/echidna.tar.gz \
      "https://github.com/crytic/echidna/releases/latest/download/echidna-linux-${ECHIDNA_ARCH}.tar.gz"; then
    tar xzf /tmp/echidna.tar.gz -C /tmp
    sudo mv /tmp/echidna /usr/local/bin/ && rm -f /tmp/echidna.tar.gz
    echo "echidna installed from release binary."
else
    echo "Release download failed — falling back to cargo build (slow, needs Rust):"
    echo "  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
    echo "  cargo install --git https://github.com/crytic/echidna --locked"
    exit 1
fi
echidna --version || true

echo "==> [7/7] Serve your fine-tuned 27B (Q4_K_M GGUF from your private HF repo)"
mkdir -p ~/models
# Download your GGUF from your private HF repo (create it first: huggingface.co/new):
#   pip3 install -q huggingface_hub
#   huggingface-cli download yourname/qwen3.6-solidity-v2 --local-dir ~/models
cat > ~/models/Modelfile <<'EOF'
FROM /root/models/qwen3.6-solidity-v2-q4_k_m.gguf
PARAMETER temperature 0.2
PARAMETER num_ctx 8192
EOF
ollama create hunter -f ~/models/Modelfile || echo "No GGUF yet — run 'ollama pull qwen3.6:27b' to serve the base, then re-create the Modelfile."

echo ""
echo "================================================================"
echo " DONE. Verify:"
echo "   curl http://localhost:11434/api/tags"
echo "   python3 eval_harness.py --model hunter --contract <file> --function <name>"
echo " stack: ollama + forge + echidna + slither  |  model: 'hunter'"
echo "================================================================"
