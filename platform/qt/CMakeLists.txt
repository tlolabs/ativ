cmake_minimum_required(VERSION 3.24)
project(ATIVQt VERSION 0.2.6 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)

find_package(Qt6 REQUIRED COMPONENTS Widgets)
find_package(Qt6 COMPONENTS Test QUIET)

add_library(ativ-qt-ui STATIC
    EngineJob.cpp
    MainWindow.cpp
    Preferences.cpp
    PreferencesDialog.cpp
    UpdateClient.cpp
)
target_link_libraries(ativ-qt-ui PUBLIC Qt6::Widgets)
target_include_directories(ativ-qt-ui PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})

if(MSVC)
    target_compile_options(ativ-qt-ui PRIVATE /W4 /permissive-)
else()
    target_compile_options(ativ-qt-ui PRIVATE -Wall -Wextra -Wpedantic)
endif()

if(APPLE)
    set(ICON ../macos/Resources/ATIV.icns)
    set_source_files_properties(${ICON} PROPERTIES MACOSX_PACKAGE_LOCATION Resources)
    qt_add_executable(ATIVQt MACOSX_BUNDLE main.cpp ${ICON})
    target_link_libraries(ATIVQt PRIVATE ativ-qt-ui)
    set_target_properties(ATIVQt PROPERTIES
        OUTPUT_NAME "ATIV Qt"
        MACOSX_BUNDLE_GUI_IDENTIFIER com.tlolabs.ativ.qt-experiment
        MACOSX_BUNDLE_BUNDLE_NAME "ATIV Qt"
        MACOSX_BUNDLE_ICON_FILE ATIV.icns
        MACOSX_BUNDLE_SHORT_VERSION_STRING ${PROJECT_VERSION}
        MACOSX_BUNDLE_BUNDLE_VERSION ${PROJECT_VERSION}
        MACOSX_BUNDLE_INFO_PLIST ${CMAKE_CURRENT_SOURCE_DIR}/Info.plist.in)
elseif(WIN32)
    set(WIN_SOURCES main.cpp ../windows/ATIV.rc)
    qt_add_executable(ATIV WIN32 ${WIN_SOURCES})
    target_link_libraries(ATIV PRIVATE ativ-qt-ui)
    set_target_properties(ATIV PROPERTIES OUTPUT_NAME "ATIV")

    add_executable(ativ-portable-update ../windows/PortableUpdate/main.cpp)
    target_compile_features(ativ-portable-update PRIVATE cxx_std_17)
    target_link_libraries(ativ-portable-update PRIVATE bcrypt crypt32 advapi32)
else()
    qt_add_executable(ATIV main.cpp)
    target_link_libraries(ATIV PRIVATE ativ-qt-ui)
    set_target_properties(ATIV PROPERTIES OUTPUT_NAME "ATIV")
endif()

if(TARGET Qt6::Test)
    enable_testing()
    qt_add_executable(ativ-qt-tests tests.cpp)
    target_link_libraries(ativ-qt-tests PRIVATE ativ-qt-ui Qt6::Test)
    add_test(NAME qt-workflow COMMAND ativ-qt-tests)
    set_tests_properties(qt-workflow PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen" TIMEOUT 180)
endif()
