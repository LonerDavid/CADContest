#!/usr/bin/env bash
# Deploy this project to the ICCAD contest VM through the EDAUnion jump host,
# building a project-local .venv with a modern Python (the VM's default python3
# is 3.6.8, too old; this project needs >=3.7 and python3.12 is available).
#
# Run in YOUR OWN terminal (interactive: asks EDAUnion password then VM password).
#
# MODE:
#   full     (default) rsync + create .venv (REMOTE_PY) + pip install from PyPI
#            (requirements + pybind11) + build C++ + smoke test
#   upload   rsync only
#   cpp      OFFLINE: build a wheelhouse locally for the VM's Python/arch, ship it,
#            create .venv and pip install --no-index from the wheelhouse, build C++,
#            smoke test. Use when the VM cannot reach PyPI.
#   uv       rsync + install uv on the VM + uv-managed standalone Python 3.12
#            (bundles Python.h, which the system python3.12 lacks) + rebuild .venv
#            from it + pip install + build C++ + smoke test. Use when the system
#            Python has no dev headers and there is no root to install -devel.
#
# The VM login shell is tcsh, so every remote step is a quoted here-doc piped to
# `bash -s` (shell-agnostic).
#
# Env vars: JUMP, JUMP_PORT, VM_USER, VM_HOST, DEST, CONFIG, MODE, DELETE,
#           REMOTE_PY (VM python, default python3.12), PYTAG (wheel tag, default 312)
set -euo pipefail

JUMP="${JUMP:-eda26s06@edaunion.ee.ntu.edu.tw}"
JUMP_PORT="${JUMP_PORT:-40061}"
VM_USER="${VM_USER:-cada1089}"
VM_HOST="${VM_HOST:-140.110.214.90}"
DEST="${DEST:-alpha_test_submission}"
CONFIG="${CONFIG:-config.example.yaml}"
MODE="${MODE:-full}"
DELETE="${DELETE:-0}"
REMOTE_PY="${REMOTE_PY:-python3.12}"
PYTAG="${PYTAG:-312}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
JUMP_OPT="-J ${JUMP}:${JUMP_PORT}"

DELETE_OPT=""
if [[ "${DELETE}" == "1" ]]; then
  DELETE_OPT="--delete"
  echo "==> DELETE mode: ${DEST}/ will be made IDENTICAL to local (extra files removed)"
fi

rsync_project() {
  echo "==> rsync ${ROOT}/  ->  ${VM_USER}@${VM_HOST}:${DEST}/ (via ${JUMP})"
  rsync -avz --progress ${DELETE_OPT} \
    --exclude '.git/' --exclude '.venv/' --exclude 'output/' \
    --exclude '__pycache__/' --exclude '.DS_Store' --exclude '._*' \
    --exclude '.idea/' --exclude '.vscode/' --exclude '*.so' \
    --exclude 'config.yaml' --exclude '*.log' --exclude '*_out.v' \
    --exclude 'abc.history' --exclude 'build/' --exclude '*.egg-info/' \
    --exclude 'wheelhouse/' \
    -e "ssh ${JUMP_OPT}" \
    "${ROOT}/" "${VM_USER}@${VM_HOST}:${DEST}/"
}

smoke_test() {
  echo "==> smoke test (test01) via ./cada1089_alpha, config=${CONFIG}"
  ssh ${JUMP_OPT} "${VM_USER}@${VM_HOST}" "bash -s '${DEST}' '${CONFIG}'" <<'REMOTE'
DEST="$1"; CONFIG="$2"
cd "$DEST" || exit 1
chmod +x cada1089_alpha 2>/dev/null || true
echo "venv python: $(.venv/bin/python --version 2>&1)"
cat testcase/test01/prompt.txt | ./cada1089_alpha -config "$CONFIG" 2>&1 | head -15 || true
REMOTE
}

rsync_project

if [[ "${MODE}" == "upload" ]]; then
  echo "==> upload-only mode; done."
  exit 0
fi

if [[ "${MODE}" == "cpp" ]]; then
  echo "==> OFFLINE build: assembling wheelhouse locally for ${REMOTE_PY} (cp${PYTAG}, linux x86_64)"
  TMP="$(mktemp -d)"; trap 'rm -rf "${TMP}"' EXIT
  python3 -m pip download -r "${ROOT}/requirements.txt" pybind11 setuptools wheel \
    --only-binary=:all: --python-version "${PYTAG}" \
    --platform manylinux2014_x86_64 --platform manylinux_2_17_x86_64 \
    --platform manylinux_2_28_x86_64 --platform any \
    -d "${TMP}/wheelhouse"
  echo "    wheels: $(ls "${TMP}/wheelhouse" | wc -l | tr -d ' ')"
  echo "    shipping wheelhouse to VM ..."
  rsync -avz --progress -e "ssh ${JUMP_OPT}" \
    "${TMP}/wheelhouse/" "${VM_USER}@${VM_HOST}:${DEST}/wheelhouse/"

  echo "==> create venv + offline install + build on the VM"
  ssh ${JUMP_OPT} "${VM_USER}@${VM_HOST}" "bash -s '${DEST}' '${REMOTE_PY}'" <<'REMOTE'
DEST="$1"; PY="$2"
cd "$DEST" || { echo "ERROR: cannot cd $DEST"; exit 1; }
command -v "$PY" >/dev/null 2>&1 || { echo "ERROR: $PY not found on VM"; exit 1; }
rm -f eda_core*darwin*.so 2>/dev/null || true
[ -x .venv/bin/python ] || "$PY" -m venv .venv
.venv/bin/python -m pip install --no-index --find-links wheelhouse \
  -r requirements.txt pybind11 setuptools wheel || { echo "ERROR: offline pip install failed"; exit 1; }
rm -rf build eda_core*.so 2>/dev/null || true
.venv/bin/python setup.py build_ext --inplace 2>&1 | tail -6 || echo "WARN: build_ext failed"
ls eda_core*.so >/dev/null 2>&1 \
  && echo "OK: C++ extension built -> $(ls eda_core*.so)" \
  || echo "WARN: no .so built (pure-Python fallback)"
rm -rf wheelhouse
REMOTE
elif [[ "${MODE}" == "uv" ]]; then
  echo "==> UV build: install uv + standalone Python 3.12 (bundles Python.h) + build on VM"
  ssh ${JUMP_OPT} "${VM_USER}@${VM_HOST}" "bash -s '${DEST}'" <<'REMOTE'
DEST="$1"
cd "$DEST" || { echo "ERROR: cannot cd $DEST"; exit 1; }
UV="$(command -v uv || true)"
if [ -z "$UV" ]; then
  echo "Installing uv ..."
  curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1 || { echo "ERROR: uv install failed"; exit 1; }
  UV="$HOME/.local/bin/uv"
fi
[ -x "$UV" ] || { echo "ERROR: uv not found after install"; exit 1; }
echo "uv: $($UV --version 2>&1)"
"$UV" python install 3.12 || { echo "ERROR: uv python install failed"; exit 1; }
rm -f eda_core*darwin*.so 2>/dev/null || true
# Old .venv was built from a headerless system python; rebuild from uv's python.
rm -rf .venv
"$UV" venv --python 3.12 .venv || { echo "ERROR: uv venv failed"; exit 1; }
"$UV" pip install --python .venv/bin/python -r requirements.txt pybind11 setuptools wheel \
  || { echo "ERROR: uv pip install failed"; exit 1; }
echo "Python.h: $(.venv/bin/python -c 'import sysconfig,os;p=os.path.join(sysconfig.get_path("include"),"Python.h");print(p if os.path.exists(p) else "MISSING")')"
rm -rf build eda_core*.so 2>/dev/null || true
.venv/bin/python setup.py build_ext --inplace 2>&1 | tail -6 || echo "WARN: build_ext failed"
ls eda_core*.so >/dev/null 2>&1 \
  && echo "OK: C++ extension built -> $(ls eda_core*.so)" \
  || echo "WARN: no .so built (pure-Python fallback)"
REMOTE
else
  echo "==> ONLINE build: create venv (${REMOTE_PY}) + pip install from PyPI + build on VM"
  ssh ${JUMP_OPT} "${VM_USER}@${VM_HOST}" "bash -s '${DEST}' '${REMOTE_PY}'" <<'REMOTE'
DEST="$1"; PY="$2"
cd "$DEST" || { echo "ERROR: cannot cd $DEST"; exit 1; }
command -v "$PY" >/dev/null 2>&1 || { echo "ERROR: $PY not found on VM"; exit 1; }
echo "Using: $($PY --version 2>&1)"
rm -f eda_core*darwin*.so 2>/dev/null || true
[ -x .venv/bin/python ] || "$PY" -m venv .venv
.venv/bin/python -m pip install -q --upgrade pip setuptools wheel
.venv/bin/python -m pip install -r requirements.txt pybind11 \
  || { echo "ERROR: pip install failed (no PyPI access? try MODE=cpp)"; exit 1; }
rm -rf build eda_core*.so 2>/dev/null || true
.venv/bin/python setup.py build_ext --inplace 2>&1 | tail -6 || echo "WARN: build_ext failed"
ls eda_core*.so >/dev/null 2>&1 \
  && echo "OK: C++ extension built -> $(ls eda_core*.so)" \
  || echo "WARN: no .so built (pure-Python fallback)"
REMOTE
fi

smoke_test
echo "==> done"
