# This file is modified from duktapeConfig.cmake

# - Try to find LIBZMQ
# Once done this will define
#
#  LIBZMQ_FOUND - system has LIBZMQ
#  LIBZMQ_INCLUDE_DIRS - the LIBZMQ include directory
#  LIBZMQ_LIBRARIES - Link these to use LIBZMQ
#  LIBZMQ_DEFINITIONS - Compiler switches required for using LIBZMQ
#

PKG_CHECK_MODULES(PC_LIBZMQ QUIET zmq libzmq)

find_path(LIBZMQ_INCLUDE_DIR zmq.hpp
    HINTS ${PC_LIBZMQ_INCLUDEDIR} ${PC_LIBZMQ_INCLUDE_DIRS}
    PATH_SUFFIXES zmq)

find_library(LIBZMQ_LIBRARY
    NAMES zmq libzmq
    HINTS ${PC_LIBZMQ_LIBDIR} ${PC_LIBZMQ_LIBRARY_DIRS})

include(FindPackageHandleStandardArgs)
FIND_PACKAGE_HANDLE_STANDARD_ARGS(libzmq
    REQUIRED_VARS LIBZMQ_LIBRARY LIBZMQ_INCLUDE_DIR)

if (LIBZMQ_FOUND)
    set (LIBZMQ_LIBRARIES ${LIBZMQ_LIBRARY})
    set (LIBZMQ_INCLUDE_DIRS ${LIBZMQ_INCLUDE_DIR} )
endif ()

MARK_AS_ADVANCED(
    LIBZMQ_INCLUDE_DIR
    LIBZMQ_LIBRARY
)
