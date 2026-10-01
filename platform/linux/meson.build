project('ativ-linux', 'c', version: run_command('python3', '-c', 'import pathlib,tomllib; print(tomllib.loads(pathlib.Path(__import__("sys").argv[1]).read_text())["workspace"]["package"]["version"])', meson.current_source_dir() / '../../Cargo.toml', check: true).stdout().strip(), default_options: ['c_std=c17', 'warning_level=3'])

gtk = dependency('gtk4', version: '>=4.10')
adw = dependency('libadwaita-1', version: '>=1.4')
json_glib = dependency('json-glib-1.0')
engine_path = get_option('engine_path')

executable(
  'ativ',
  'src/main.c',
  dependencies: [gtk, adw, json_glib],
  c_args: ['-DATIV_ENGINE_PATH="' + engine_path + '"', '-DATIV_APP_ID="' + get_option('app_id') + '"'],
  install: true,
)

install_data('data/com.tlolabs.ativ.desktop', install_dir: get_option('datadir') / 'applications')
install_data('data/com.tlolabs.ativ.metainfo.xml', install_dir: get_option('datadir') / 'metainfo')

foreach size : [16, 24, 32, 48, 64, 128, 256, 512]
  install_data('data/icons/' + size.to_string() + '.png', install_dir: get_option('datadir') / 'icons/hicolor' / (size.to_string() + 'x' + size.to_string()) / 'apps', rename: 'com.tlolabs.ativ.png')
endforeach
