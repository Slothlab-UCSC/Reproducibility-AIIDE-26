cmake_minimum_required(VERSION 3.20)
project(PAIndemic LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

add_compile_options(-Wall -Wextra)

# --- Core engine library ---
add_library(paindemic
  src/map_data.cpp
  src/engine.cpp
  src/log.cpp
  src/heuristic.cpp
  src/agents.cpp
  src/state_io.cpp
)
target_include_directories(paindemic PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)

# --- Console driver ---
add_executable(paindemic_driver apps/driver.cpp)
target_link_libraries(paindemic_driver PRIVATE paindemic)

# --- Differential decision oracle (reads state snapshots, emits the planner's choice) ---
add_executable(paindemic_oracle apps/oracle.cpp)
target_link_libraries(paindemic_oracle PRIVATE paindemic)

# --- Tests ---
enable_testing()
add_executable(paindemic_tests
  tests/test_main.cpp
  tests/test_setup.cpp
  tests/test_actions.cpp
  tests/test_infection.cpp
  tests/test_epidemic_outbreak.cpp
  tests/test_roles.cpp
  tests/test_endconditions.cpp
  tests/test_selfplay.cpp
  tests/test_log_agents.cpp
  tests/test_planning.cpp
  tests/test_determinize.cpp
  tests/test_state_io.cpp
)
target_include_directories(paindemic_tests PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/third_party)
target_link_libraries(paindemic_tests PRIVATE paindemic)

add_test(NAME paindemic_tests COMMAND paindemic_tests)
