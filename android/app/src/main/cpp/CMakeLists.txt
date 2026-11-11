# Native build of The Devil's Revolver: the same C game code as the GBA ROM,
# with src/native/ppu.c drawing the layers into an Android bitmap.
cmake_minimum_required(VERSION 3.22.1)
project(devilsrevolver C)

set(GAME ${CMAKE_CURRENT_SOURCE_DIR}/../../../../../src)
file(GLOB ASSET_SRC ${GAME}/assets/*.c)

add_library(devilsrevolver SHARED
    jni_bridge.c
    ${GAME}/main.c
    ${GAME}/world.c
    ${GAME}/actors.c
    ${GAME}/hud.c
    ${GAME}/render.c
    ${GAME}/native/ppu.c
    ${ASSET_SRC})

target_include_directories(devilsrevolver PRIVATE ${GAME})
target_compile_definitions(devilsrevolver PRIVATE PLATFORM_NATIVE=1)
target_compile_options(devilsrevolver PRIVATE -O2 -fno-strict-aliasing -w)
target_link_libraries(devilsrevolver jnigraphics log)
