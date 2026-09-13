project('avid-linux', 'c', version: '0.2.1', default_options: ['c_std=c17', 'warning_level=3'])

gtk = dependency('gtk4', version: '>=4.10')
adw = dependency('libadwaita-1', version: '>=1.5')
json_glib = dependency('json-glib-1.0')
engine_path = get_option('engine_path')

executable(
  'avid',
  'src/main.c',
  dependencies: [gtk, adw, json_glib],
  c_args: ['-DAVID_ENGINE_PATH="' + engine_path + '"'],
  install: true,
)

install_data('data/com.tlolabs.avid.desktop', install_dir: get_option('datadir') / 'applications')
install_data('data/com.tlolabs.avid.metainfo.xml', install_dir: get_option('datadir') / 'metainfo')
