# LLM Plays RollerCoaster Tycoon

This repository contains our modified implementation of the OpenRCT2 gymnasium for machine learning models from the paper *Playing RollerCoaster Tycoon with Reinforcement Learning* (DOI: 10.1145/3723498.3723818), alongside our LLM-based gameplaying agent designed to interact with it. To run our agent, the gymnasium environment needs to be built and run and scenarios must be created within it's scenario editor that are similar to those described in the original paper.

During our use, the gymnasium environment has proved to be tricky to compile and we have only successfully completed it on Mac OS 26 using the instructions below: 


## macOS setup
Any of the following commands should be run from the root folder unless stated otherwise.

### 1. Prerequisites

- Xcode Command Line Tools (`xcode-select --install`) and Homebrew.
- CMake 3.24 or newer, a C++20 compiler, and the ZeroMQ native library.
- Python 3 and `venv`.
- Original RollerCoaster Tycoon 2 game data. An existing installation of OpenRCT2 should be enough as well.

- Required brew packages: ```brew install cmake pkg-config zeromq```
- An activated venv for python:
```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r Client/requirements.txt
```

### 2. Build the Gymnasium
CMake should download everything you need aside from ZeroMQ. These commands should work to build them:

```sh
mkdir -p Game/build/zeromq-include
cp Game/src/openrct2/zmq.h Game/src/openrct2/zmq.hpp Game/build/zeromq-include/

cmake -S Game -B Game/build \
  -DCMAKE_BUILD_TYPE=Release \
  -DLIBZMQ_INCLUDE_DIR="$PWD/Game/build/zeromq-include" \
  -DLIBZMQ_LIBRARY="$(brew --prefix zeromq)/lib/libzmq.dylib"
cmake --build Game/build --parallel 8
cmake --build Game/build --target install
codesign --force --deep --sign - Game/build/OpenRCT2.app
Game/build/OpenRCT2.app/Contents/MacOS/OpenRCT2 --version
```
*The codesign step is required for Apple Silicon (and maybe other?) systems in order for the system to allow it to launch.

### 3. Start the LLM agent

From `Client/`, with the virtual environment active:

```sh
cp -n example.env .env
# Edit .env and replace the placeholder with your OpenAI API key.
python LLMRCT.py
```

`LLMRCT.py` defaults to `gpt-4o`.

The agent's prompt assumes a specially prepared park with unlimited money and free rides as described in the original paper. These will need to be created yourself through the custom scenario editor. 


## Other platforms
We have not tested any other platforms, but similar instructions should apply.
