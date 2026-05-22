# cadcontest

C++ and Python code for CAD contest solutions and tooling.

## Repository layout

| Path | Description |
|------|-------------|
| `cpp/` | C++ sources, headers, and build files |
| `python/` | Python scripts and packages |

Adjust these directories as the project grows.

## Requirements

- **C++**: A C++17 (or newer) compiler and CMake 3.16+ (if using CMake)
- **Python**: Python 3.10+

## Building (C++)

```bash
mkdir -p build && cd build
cmake ..
cmake --build .
```

If you use a plain Makefile instead of CMake, run `make` from the appropriate directory.

## Python setup

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Create `requirements.txt` when you add dependencies.

## License

Add a license file when you are ready to publish or share this repository.
