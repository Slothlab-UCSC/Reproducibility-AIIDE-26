import platform

if 'macOS' in platform.platform():
    #Path to .app/Contents/MacOS/OpenRCT2
    RCT_EXECUTABLE = "/Users/thomas/Desktop/untitled folder 5/build/OpenRCT2.app/Contents/MacOS/OpenRCT2"
    # Where everything else is. Should have small_parks/ in it. (Other stuff???)
    BASE_DIR = "/Users/thomas/Downloads/rctrl-main"
else:
    RCT_EXECUTABLE = "/home/jcampbell/Desktop/openrct2-pathrl-ub/build/openrct2"
    BASE_DIR = "/home/jcampbell/Desktop/pathrl"

# IDK what this is yet.
PARK_PATH = BASE_DIR + "/"

# In this version, the park path is wherever the parks are stored. Like "Leafy Lake (with path).park"
PARK_DIR = f"{BASE_DIR}/small_parks"