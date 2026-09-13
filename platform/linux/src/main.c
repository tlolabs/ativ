#include <adwaita.h>
#include <json-glib/json-glib.h>
#include <glib/gstdio.h>

#ifndef ATIV_ENGINE_PATH
#define ATIV_ENGINE_PATH "ativ-engine"
#endif

typedef struct {
  gchar *platform;
  gchar *aspect;
  guint width;
  guint height;
} Preset;

typedef struct {
  AdwApplicationWindow *window;
  GtkEntry *image_entry;
  GtkEntry *audio_entry;
  GtkEntry *output_entry;
  GtkDropDown *platform_drop;
  GtkDropDown *aspect_drop;
  GtkDropDown *resolution_drop;
  GtkEntry *bitrate_entry;
  GtkSpinButton *fps_spin;
  GtkCheckButton *flip_h;
  GtkCheckButton *flip_v;
  GtkPicture *preview;
  GtkLabel *duration_label;
  GtkLabel *status_label;
  GtkProgressBar *progress;
  GtkButton *render_button;
  GPtrArray *presets;
  GSubprocess *render_process;
  GDataInputStream *render_output;
  gchar *engine;
  gchar *preview_path;
  guint preview_generation;
  gboolean render_owner_ref_held;
  gboolean close_after_render;
} AtivWindow;

typedef struct {
  AtivWindow *window;
  AdwApplicationWindow *owner;
  gchar *path;
  guint generation;
} PreviewRequest;

static void refresh_preview(AtivWindow *self);
static void update_aspects(AtivWindow *self);

static void preset_free(gpointer data) {
  Preset *preset = data;
  g_free(preset->platform);
  g_free(preset->aspect);
  g_free(preset);
}

static void ativ_window_free(gpointer data) {
  AtivWindow *self = data;
  if (self->render_process) {
    GOutputStream *input = g_subprocess_get_stdin_pipe(self->render_process);
    g_output_stream_write_all(input, "cancel\n", 7, NULL, NULL, NULL);
  }
  g_clear_object(&self->render_output);
  g_clear_object(&self->render_process);
  g_clear_pointer(&self->presets, g_ptr_array_unref);
  g_clear_pointer(&self->engine, g_free);
  if (self->preview_path) g_unlink(self->preview_path);
  g_clear_pointer(&self->preview_path, g_free);
  g_free(self);
}

static gboolean close_requested(GtkWindow *window, gpointer user_data) {
  AtivWindow *self = user_data;
  if (!self->render_process) return FALSE;
  GOutputStream *input = g_subprocess_get_stdin_pipe(self->render_process);
  g_output_stream_write_all(input, "cancel\n", 7, NULL, NULL, NULL);
  self->close_after_render = TRUE;
  gtk_label_set_text(self->status_label, "Stopping safely before closing…");
  return TRUE;
}

static gchar *resolve_engine(void) {
  const gchar *configured = g_getenv("ATIV_ENGINE_PATH");
  if (configured && *configured) return g_strdup(configured);
  if (g_file_test(ATIV_ENGINE_PATH, G_FILE_TEST_IS_EXECUTABLE)) return g_strdup(ATIV_ENGINE_PATH);
  return g_find_program_in_path("ativ-engine");
}

static gboolean parse_event(const gchar *line, JsonObject **object_out) {
  g_autoptr(JsonParser) parser = json_parser_new();
  if (!json_parser_load_from_data(parser, line, -1, NULL)) return FALSE;
  JsonNode *root = json_parser_get_root(parser);
  if (!JSON_NODE_HOLDS_OBJECT(root)) return FALSE;
  *object_out = json_object_ref(json_node_get_object(root));
  return TRUE;
}

static gchar *selected_text(GtkDropDown *drop) {
  GtkStringObject *item = GTK_STRING_OBJECT(gtk_drop_down_get_selected_item(drop));
  return item ? g_strdup(gtk_string_object_get_string(item)) : NULL;
}

static Preset *selected_preset(AtivWindow *self) {
  g_autofree gchar *platform = selected_text(self->platform_drop);
  g_autofree gchar *aspect = selected_text(self->aspect_drop);
  g_autofree gchar *resolution = selected_text(self->resolution_drop);
  if (!platform || !aspect || !resolution) return NULL;
  for (guint i = 0; i < self->presets->len; i++) {
    Preset *preset = g_ptr_array_index(self->presets, i);
    g_autofree gchar *candidate = g_strdup_printf("%u × %u", preset->width, preset->height);
    if (g_str_equal(platform, preset->platform) && g_str_equal(aspect, preset->aspect) && g_str_equal(resolution, candidate)) return preset;
  }
  return NULL;
}

static gboolean model_contains(GtkStringList *list, const gchar *value) {
  for (guint i = 0; i < g_list_model_get_n_items(G_LIST_MODEL(list)); i++) {
    g_autoptr(GtkStringObject) item = g_list_model_get_item(G_LIST_MODEL(list), i);
    if (g_str_equal(gtk_string_object_get_string(item), value)) return TRUE;
  }
  return FALSE;
}

static void update_resolutions(AtivWindow *self) {
  g_autofree gchar *platform = selected_text(self->platform_drop);
  g_autofree gchar *aspect = selected_text(self->aspect_drop);
  GtkStringList *values = gtk_string_list_new(NULL);
  for (guint i = 0; i < self->presets->len; i++) {
    Preset *preset = g_ptr_array_index(self->presets, i);
    if (platform && aspect && g_str_equal(platform, preset->platform) && g_str_equal(aspect, preset->aspect)) {
      g_autofree gchar *resolution = g_strdup_printf("%u × %u", preset->width, preset->height);
      if (!model_contains(values, resolution)) gtk_string_list_append(values, resolution);
    }
  }
  gtk_drop_down_set_model(self->resolution_drop, G_LIST_MODEL(values));
  gtk_drop_down_set_selected(self->resolution_drop, 0);
  g_object_unref(values);
  refresh_preview(self);
}

static void update_aspects(AtivWindow *self) {
  g_autofree gchar *platform = selected_text(self->platform_drop);
  GtkStringList *values = gtk_string_list_new(NULL);
  for (guint i = 0; i < self->presets->len; i++) {
    Preset *preset = g_ptr_array_index(self->presets, i);
    if (platform && g_str_equal(platform, preset->platform) && !model_contains(values, preset->aspect)) gtk_string_list_append(values, preset->aspect);
  }
  gtk_drop_down_set_model(self->aspect_drop, G_LIST_MODEL(values));
  gtk_drop_down_set_selected(self->aspect_drop, 0);
  g_object_unref(values);
  update_resolutions(self);
}

static gboolean load_presets(AtivWindow *self) {
  const gchar *argv[] = {self->engine, "presets", NULL};
  g_autoptr(GError) error = NULL;
  g_autoptr(GSubprocess) process = g_subprocess_newv(argv, G_SUBPROCESS_FLAGS_STDOUT_PIPE, &error);
  if (!process) return FALSE;
  g_autofree gchar *stdout_text = NULL;
  if (!g_subprocess_communicate_utf8(process, NULL, NULL, &stdout_text, NULL, &error)) return FALSE;
  g_autoptr(JsonObject) object = NULL;
  if (!parse_event(stdout_text, &object) || !json_object_has_member(object, "items")) return FALSE;
  JsonArray *items = json_object_get_array_member(object, "items");
  GtkStringList *platforms = gtk_string_list_new(NULL);
  for (guint i = 0; i < json_array_get_length(items); i++) {
    JsonObject *item = json_array_get_object_element(items, i);
    Preset *preset = g_new0(Preset, 1);
    preset->platform = g_strdup(json_object_get_string_member(item, "platform"));
    preset->aspect = g_strdup(json_object_get_string_member(item, "aspect"));
    preset->width = (guint)json_object_get_int_member(item, "width");
    preset->height = (guint)json_object_get_int_member(item, "height");
    g_ptr_array_add(self->presets, preset);
    if (!model_contains(platforms, preset->platform)) gtk_string_list_append(platforms, preset->platform);
  }
  gtk_drop_down_set_model(self->platform_drop, G_LIST_MODEL(platforms));
  gtk_drop_down_set_selected(self->platform_drop, 0);
  g_object_unref(platforms);
  update_aspects(self);
  return self->presets->len > 0;
}

static void show_error(AtivWindow *self, const gchar *message) {
  AdwAlertDialog *dialog = adw_alert_dialog_new("A.T.I.V. couldn’t complete the operation", message);
  adw_alert_dialog_add_response(dialog, "ok", "OK");
  adw_alert_dialog_set_default_response(dialog, "ok");
  adw_dialog_present(ADW_DIALOG(dialog), GTK_WIDGET(self->window));
}

static void suggest_output(AtivWindow *self, const gchar *source) {
  if (*gtk_editable_get_text(GTK_EDITABLE(self->output_entry))) return;
  g_autofree gchar *directory = g_path_get_dirname(source);
  g_autofree gchar *base = g_path_get_basename(source);
  gchar *dot = strrchr(base, '.');
  if (dot) *dot = '\0';
  g_autofree gchar *name = g_strconcat(base, ".mp4", NULL);
  g_autofree gchar *output = g_build_filename(directory, name, NULL);
  gtk_editable_set_text(GTK_EDITABLE(self->output_entry), output);
}

static void preview_done(GObject *source, GAsyncResult *result, gpointer user_data) {
  PreviewRequest *request = user_data;
  AtivWindow *self = request->window;
  g_autoptr(GError) error = NULL;
  if (g_subprocess_wait_check_finish(G_SUBPROCESS(source), result, &error) && request->generation == self->preview_generation) {
    if (self->preview_path) g_unlink(self->preview_path);
    g_free(self->preview_path);
    self->preview_path = g_strdup(request->path);
    gtk_picture_set_filename(self->preview, self->preview_path);
  } else {
    g_unlink(request->path);
  }
  g_free(request->path);
  g_object_unref(request->owner);
  g_free(request);
}

static void refresh_preview(AtivWindow *self) {
  const gchar *image = gtk_editable_get_text(GTK_EDITABLE(self->image_entry));
  Preset *preset = selected_preset(self);
  if (!*image || !preset) return;
  g_autofree gchar *directory = g_build_filename(g_get_user_cache_dir(), "ativ", NULL);
  g_mkdir_with_parents(directory, 0700);
  guint generation = ++self->preview_generation;
  g_autofree gchar *name = g_strdup_printf("preview-%u.png", generation);
  g_autofree gchar *output = g_build_filename(directory, name, NULL);
  guint width = preset->width >= preset->height ? 360 : MAX(2, (360 * preset->width / preset->height) & ~1u);
  guint height = preset->height >= preset->width ? 360 : MAX(2, (360 * preset->height / preset->width) & ~1u);
  g_autofree gchar *width_text = g_strdup_printf("%u", width);
  g_autofree gchar *height_text = g_strdup_printf("%u", height);
  const gchar *argv[16] = {self->engine, "preview", "--image", image, "--output", output, "--width", width_text, "--height", height_text, NULL};
  guint n = 10;
  if (gtk_check_button_get_active(self->flip_h)) argv[n++] = "--flip-horizontal";
  if (gtk_check_button_get_active(self->flip_v)) argv[n++] = "--flip-vertical";
  argv[n] = NULL;
  g_autoptr(GError) error = NULL;
  GSubprocess *process = g_subprocess_newv(argv, G_SUBPROCESS_FLAGS_NONE, &error);
  if (process) {
    PreviewRequest *request = g_new0(PreviewRequest, 1);
    request->window = self;
    request->owner = g_object_ref(self->window);
    request->path = g_strdup(output);
    request->generation = generation;
    g_subprocess_wait_check_async(process, NULL, preview_done, request);
    g_object_unref(process);
  }
}

static void image_chosen(GObject *source, GAsyncResult *result, gpointer user_data) {
  AtivWindow *self = user_data;
  g_autoptr(GError) error = NULL;
  g_autoptr(GFile) file = gtk_file_dialog_open_finish(GTK_FILE_DIALOG(source), result, &error);
  if (!file) return;
  g_autofree gchar *path = g_file_get_path(file);
  gtk_editable_set_text(GTK_EDITABLE(self->image_entry), path);
  suggest_output(self, path);
  refresh_preview(self);
}

static void audio_chosen(GObject *source, GAsyncResult *result, gpointer user_data) {
  AtivWindow *self = user_data;
  g_autoptr(GError) error = NULL;
  g_autoptr(GFile) file = gtk_file_dialog_open_finish(GTK_FILE_DIALOG(source), result, &error);
  if (!file) return;
  g_autofree gchar *path = g_file_get_path(file);
  gtk_editable_set_text(GTK_EDITABLE(self->audio_entry), path);
  suggest_output(self, path);
  gtk_label_set_text(self->duration_label, "Duration will be verified before rendering");
}

static void output_chosen(GObject *source, GAsyncResult *result, gpointer user_data) {
  AtivWindow *self = user_data;
  g_autoptr(GError) error = NULL;
  g_autoptr(GFile) file = gtk_file_dialog_save_finish(GTK_FILE_DIALOG(source), result, &error);
  if (!file) return;
  g_autofree gchar *path = g_file_get_path(file);
  gtk_editable_set_text(GTK_EDITABLE(self->output_entry), path);
}

static void choose_image(GtkButton *button, gpointer user_data) {
  GtkFileDialog *dialog = gtk_file_dialog_new();
  gtk_file_dialog_set_title(dialog, "Choose an image");
  g_autoptr(GtkFileFilter) filter = gtk_file_filter_new();
  gtk_file_filter_set_name(filter, "Images");
  gtk_file_filter_add_mime_type(filter, "image/*");
  g_autoptr(GListStore) filters = g_list_store_new(GTK_TYPE_FILE_FILTER);
  g_list_store_append(filters, filter);
  gtk_file_dialog_set_filters(dialog, G_LIST_MODEL(filters));
  gtk_file_dialog_open(dialog, GTK_WINDOW(((AtivWindow *)user_data)->window), NULL, image_chosen, user_data);
  g_object_unref(dialog);
}

static void choose_audio(GtkButton *button, gpointer user_data) {
  GtkFileDialog *dialog = gtk_file_dialog_new();
  gtk_file_dialog_set_title(dialog, "Choose an audio recording");
  g_autoptr(GtkFileFilter) filter = gtk_file_filter_new();
  gtk_file_filter_set_name(filter, "Audio");
  gtk_file_filter_add_mime_type(filter, "audio/*");
  g_autoptr(GListStore) filters = g_list_store_new(GTK_TYPE_FILE_FILTER);
  g_list_store_append(filters, filter);
  gtk_file_dialog_set_filters(dialog, G_LIST_MODEL(filters));
  gtk_file_dialog_open(dialog, GTK_WINDOW(((AtivWindow *)user_data)->window), NULL, audio_chosen, user_data);
  g_object_unref(dialog);
}

static void choose_output(GtkButton *button, gpointer user_data) {
  GtkFileDialog *dialog = gtk_file_dialog_new();
  gtk_file_dialog_set_title(dialog, "Save video");
  gtk_file_dialog_set_initial_name(dialog, "video.mp4");
  g_autoptr(GtkFileFilter) filter = gtk_file_filter_new();
  gtk_file_filter_set_name(filter, "MP4 video");
  gtk_file_filter_add_pattern(filter, "*.mp4");
  g_autoptr(GListStore) filters = g_list_store_new(GTK_TYPE_FILE_FILTER);
  g_list_store_append(filters, filter);
  gtk_file_dialog_set_filters(dialog, G_LIST_MODEL(filters));
  gtk_file_dialog_save(dialog, GTK_WINDOW(((AtivWindow *)user_data)->window), NULL, output_chosen, user_data);
  g_object_unref(dialog);
}

static void render_finished(GObject *source, GAsyncResult *result, gpointer user_data) {
  AtivWindow *self = user_data;
  g_autoptr(GError) error = NULL;
  gboolean success = g_subprocess_wait_check_finish(G_SUBPROCESS(source), result, &error);
  gboolean cancelled = g_subprocess_get_if_exited(G_SUBPROCESS(source)) && g_subprocess_get_exit_status(G_SUBPROCESS(source)) == 130;
  gboolean close_after_render = self->close_after_render;
  gtk_widget_set_sensitive(GTK_WIDGET(self->render_button), TRUE);
  gtk_button_set_label(self->render_button, "Create Video");
  g_clear_object(&self->render_output);
  g_clear_object(&self->render_process);
  if (success) {
    gtk_progress_bar_set_fraction(self->progress, 1.0);
    gtk_label_set_text(self->status_label, "Video saved successfully.");
  } else if (cancelled) {
    gtk_progress_bar_set_fraction(self->progress, 0.0);
    gtk_label_set_text(self->status_label, "Video creation stopped. The previous output was preserved.");
  } else if (error && !close_after_render) {
    gtk_progress_bar_set_fraction(self->progress, 0.0);
    gtk_label_set_text(self->status_label, "The video was not changed.");
    show_error(self, error->message);
  }
  self->close_after_render = FALSE;
  if (close_after_render) gtk_window_destroy(GTK_WINDOW(self->window));
  if (self->render_owner_ref_held) {
    self->render_owner_ref_held = FALSE;
    g_object_unref(self->window);
  }
}

static void read_render_line(GObject *source, GAsyncResult *result, gpointer user_data) {
  AtivWindow *self = user_data;
  g_autoptr(GError) error = NULL;
  gsize length = 0;
  g_autofree gchar *line = g_data_input_stream_read_line_finish_utf8(G_DATA_INPUT_STREAM(source), result, &length, &error);
  if (!line) {
    if (self->render_process) g_subprocess_wait_check_async(self->render_process, NULL, render_finished, self);
    return;
  }
  g_autoptr(JsonObject) object = NULL;
  if (parse_event(line, &object)) {
    const gchar *event = json_object_get_string_member_with_default(object, "event", "");
    if (g_str_equal(event, "progress")) {
      double fraction = json_object_get_double_member_with_default(object, "fraction", 0.0);
      gtk_progress_bar_set_fraction(self->progress, CLAMP(fraction, 0.0, 1.0));
      g_autofree gchar *text = g_strdup_printf("Creating video — %.0f%%", fraction * 100.0);
      gtk_label_set_text(self->status_label, text);
    } else if (g_str_equal(event, "stage")) {
      const gchar *stage = json_object_get_string_member_with_default(object, "stage", "working");
      gtk_label_set_text(self->status_label, stage);
    } else if (g_str_equal(event, "error")) {
      show_error(self, json_object_get_string_member_with_default(object, "message", "The media engine failed."));
    }
  }
  g_data_input_stream_read_line_async(self->render_output, G_PRIORITY_DEFAULT, NULL, read_render_line, self);
}

static void cancel_render(GtkButton *button, gpointer user_data) {
  AtivWindow *self = user_data;
  if (!self->render_process) return;
  GOutputStream *input = g_subprocess_get_stdin_pipe(self->render_process);
  g_output_stream_write_all(input, "cancel\n", 7, NULL, NULL, NULL);
  gtk_widget_set_sensitive(GTK_WIDGET(button), FALSE);
  gtk_label_set_text(self->status_label, "Stopping safely…");
}

static void start_render(GtkButton *button, gpointer user_data) {
  AtivWindow *self = user_data;
  if (self->render_process) { cancel_render(button, user_data); return; }
  Preset *preset = selected_preset(self);
  const gchar *image = gtk_editable_get_text(GTK_EDITABLE(self->image_entry));
  const gchar *audio = gtk_editable_get_text(GTK_EDITABLE(self->audio_entry));
  const gchar *output = gtk_editable_get_text(GTK_EDITABLE(self->output_entry));
  if (!preset || !*image || !*audio || !*output) { show_error(self, "Choose an image, audio recording, output destination, and format."); return; }
  g_autofree gchar *width = g_strdup_printf("%u", preset->width);
  g_autofree gchar *height = g_strdup_printf("%u", preset->height);
  g_autofree gchar *fps = g_strdup_printf("%d", gtk_spin_button_get_value_as_int(self->fps_spin));
  const gchar *argv[24] = {self->engine, "render", "--image", image, "--audio", audio, "--output", output, "--width", width, "--height", height, "--audio-bitrate", gtk_editable_get_text(GTK_EDITABLE(self->bitrate_entry)), "--fps", fps, NULL};
  guint n = 16;
  if (gtk_check_button_get_active(self->flip_h)) argv[n++] = "--flip-horizontal";
  if (gtk_check_button_get_active(self->flip_v)) argv[n++] = "--flip-vertical";
  argv[n] = NULL;
  g_autoptr(GError) error = NULL;
  self->render_process = g_subprocess_newv(argv, G_SUBPROCESS_FLAGS_STDIN_PIPE | G_SUBPROCESS_FLAGS_STDOUT_PIPE | G_SUBPROCESS_FLAGS_STDERR_MERGE, &error);
  if (!self->render_process) { show_error(self, error->message); return; }
  g_object_ref(self->window);
  self->render_owner_ref_held = TRUE;
  self->render_output = g_data_input_stream_new(g_subprocess_get_stdout_pipe(self->render_process));
  gtk_button_set_label(button, "Stop Video Creation");
  gtk_label_set_text(self->status_label, "Preparing video…");
  gtk_progress_bar_set_fraction(self->progress, 0.0);
  g_data_input_stream_read_line_async(self->render_output, G_PRIORITY_DEFAULT, NULL, read_render_line, self);
}

static GtkWidget *file_row(const gchar *label, GtkEntry **entry_out, GCallback callback, AtivWindow *self) {
  GtkWidget *box = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 8);
  GtkWidget *title = gtk_label_new(label);
  gtk_widget_set_size_request(title, 72, -1);
  gtk_label_set_xalign(GTK_LABEL(title), 0);
  GtkWidget *entry = gtk_entry_new();
  gtk_editable_set_editable(GTK_EDITABLE(entry), FALSE);
  gtk_widget_set_hexpand(entry, TRUE);
  GtkWidget *button = gtk_button_new_with_label("Choose…");
  g_signal_connect(button, "clicked", callback, self);
  gtk_box_append(GTK_BOX(box), title);
  gtk_box_append(GTK_BOX(box), entry);
  gtk_box_append(GTK_BOX(box), button);
  *entry_out = GTK_ENTRY(entry);
  return box;
}

static void drop_changed(GObject *object, GParamSpec *pspec, gpointer user_data) {
  update_aspects(user_data);
}

static void aspect_changed(GObject *object, GParamSpec *pspec, gpointer user_data) {
  update_resolutions(user_data);
}

static void activate(GtkApplication *application, gpointer user_data) {
  AtivWindow *self = g_new0(AtivWindow, 1);
  self->presets = g_ptr_array_new_with_free_func(preset_free);
  self->engine = resolve_engine();
  self->window = ADW_APPLICATION_WINDOW(adw_application_window_new(application));
  g_signal_connect(self->window, "close-request", G_CALLBACK(close_requested), self);
  gtk_window_set_title(GTK_WINDOW(self->window), "A.T.I.V. — Audio Visual Integration & Distribution");
  gtk_window_set_default_size(GTK_WINDOW(self->window), 980, 700);

  GtkWidget *toolbar = adw_toolbar_view_new();
  GtkWidget *header = adw_header_bar_new();
  adw_header_bar_set_title_widget(ADW_HEADER_BAR(header), adw_window_title_new("A.T.I.V.", "Audio Visual Integration & Distribution"));
  adw_toolbar_view_add_top_bar(ADW_TOOLBAR_VIEW(toolbar), header);
  GtkWidget *split = gtk_paned_new(GTK_ORIENTATION_HORIZONTAL);
  adw_toolbar_view_set_content(ADW_TOOLBAR_VIEW(toolbar), split);
  adw_application_window_set_content(self->window, toolbar);

  GtkWidget *controls = gtk_box_new(GTK_ORIENTATION_VERTICAL, 14);
  gtk_widget_set_margin_start(controls, 24); gtk_widget_set_margin_end(controls, 24);
  gtk_widget_set_margin_top(controls, 24); gtk_widget_set_margin_bottom(controls, 24);
  gtk_paned_set_start_child(GTK_PANED(split), controls);
  gtk_paned_set_resize_start_child(GTK_PANED(split), TRUE);
  gtk_paned_set_shrink_start_child(GTK_PANED(split), FALSE);

  gtk_box_append(GTK_BOX(controls), file_row("Image", &self->image_entry, G_CALLBACK(choose_image), self));
  gtk_box_append(GTK_BOX(controls), file_row("Audio", &self->audio_entry, G_CALLBACK(choose_audio), self));
  self->duration_label = GTK_LABEL(gtk_label_new("No audio selected"));
  gtk_label_set_xalign(self->duration_label, 0); gtk_box_append(GTK_BOX(controls), GTK_WIDGET(self->duration_label));
  gtk_box_append(GTK_BOX(controls), file_row("Output", &self->output_entry, G_CALLBACK(choose_output), self));

  self->platform_drop = GTK_DROP_DOWN(gtk_drop_down_new(NULL, NULL));
  self->aspect_drop = GTK_DROP_DOWN(gtk_drop_down_new(NULL, NULL));
  self->resolution_drop = GTK_DROP_DOWN(gtk_drop_down_new(NULL, NULL));
  GtkWidget *formats = gtk_box_new(GTK_ORIENTATION_VERTICAL, 8);
  gtk_box_append(GTK_BOX(formats), gtk_label_new("Social media outlet")); gtk_box_append(GTK_BOX(formats), GTK_WIDGET(self->platform_drop));
  gtk_box_append(GTK_BOX(formats), gtk_label_new("Aspect ratio")); gtk_box_append(GTK_BOX(formats), GTK_WIDGET(self->aspect_drop));
  gtk_box_append(GTK_BOX(formats), gtk_label_new("Resolution")); gtk_box_append(GTK_BOX(formats), GTK_WIDGET(self->resolution_drop));
  gtk_box_append(GTK_BOX(controls), formats);

  self->bitrate_entry = GTK_ENTRY(gtk_entry_new()); gtk_editable_set_text(GTK_EDITABLE(self->bitrate_entry), "128k");
  self->fps_spin = GTK_SPIN_BUTTON(gtk_spin_button_new_with_range(1, 240, 1)); gtk_spin_button_set_value(self->fps_spin, 30);
  GtkWidget *options = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 12);
  gtk_box_append(GTK_BOX(options), gtk_label_new("Audio bitrate")); gtk_box_append(GTK_BOX(options), GTK_WIDGET(self->bitrate_entry));
  gtk_box_append(GTK_BOX(options), gtk_label_new("FPS")); gtk_box_append(GTK_BOX(options), GTK_WIDGET(self->fps_spin));
  gtk_box_append(GTK_BOX(controls), options);
  self->flip_h = GTK_CHECK_BUTTON(gtk_check_button_new_with_label("Flip horizontally"));
  self->flip_v = GTK_CHECK_BUTTON(gtk_check_button_new_with_label("Flip vertically"));
  GtkWidget *flips = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 12); gtk_box_append(GTK_BOX(flips), GTK_WIDGET(self->flip_h)); gtk_box_append(GTK_BOX(flips), GTK_WIDGET(self->flip_v)); gtk_box_append(GTK_BOX(controls), flips);
  self->progress = GTK_PROGRESS_BAR(gtk_progress_bar_new()); gtk_widget_set_hexpand(GTK_WIDGET(self->progress), TRUE); gtk_box_append(GTK_BOX(controls), GTK_WIDGET(self->progress));
  self->status_label = GTK_LABEL(gtk_label_new("Choose an image and audio recording.")); gtk_label_set_xalign(self->status_label, 0); gtk_label_set_wrap(self->status_label, TRUE); gtk_box_append(GTK_BOX(controls), GTK_WIDGET(self->status_label));
  self->render_button = GTK_BUTTON(gtk_button_new_with_label("Create Video")); gtk_widget_add_css_class(GTK_WIDGET(self->render_button), "suggested-action"); gtk_widget_set_size_request(GTK_WIDGET(self->render_button), -1, 42); g_signal_connect(self->render_button, "clicked", G_CALLBACK(start_render), self); gtk_box_append(GTK_BOX(controls), GTK_WIDGET(self->render_button));

  GtkWidget *preview_box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 12); gtk_widget_set_margin_start(preview_box, 24); gtk_widget_set_margin_end(preview_box, 24); gtk_widget_set_margin_top(preview_box, 24); gtk_widget_set_margin_bottom(preview_box, 24);
  GtkWidget *preview_title = gtk_label_new("Preview"); gtk_widget_add_css_class(preview_title, "title-2"); gtk_box_append(GTK_BOX(preview_box), preview_title);
  self->preview = GTK_PICTURE(gtk_picture_new()); gtk_picture_set_can_shrink(self->preview, TRUE); gtk_picture_set_content_fit(self->preview, GTK_CONTENT_FIT_CONTAIN); gtk_widget_set_size_request(GTK_WIDGET(self->preview), 360, 360); gtk_box_append(GTK_BOX(preview_box), GTK_WIDGET(self->preview));
  gtk_paned_set_end_child(GTK_PANED(split), preview_box);

  g_signal_connect(self->platform_drop, "notify::selected", G_CALLBACK(drop_changed), self);
  g_signal_connect(self->aspect_drop, "notify::selected", G_CALLBACK(aspect_changed), self);
  g_signal_connect_swapped(self->resolution_drop, "notify::selected", G_CALLBACK(refresh_preview), self);
  g_signal_connect_swapped(self->flip_h, "toggled", G_CALLBACK(refresh_preview), self);
  g_signal_connect_swapped(self->flip_v, "toggled", G_CALLBACK(refresh_preview), self);

  if (!self->engine || !load_presets(self)) {
    gtk_widget_set_sensitive(GTK_WIDGET(self->render_button), FALSE);
    gtk_label_set_text(self->status_label, "The A.T.I.V. media engine is missing or damaged. Reinstall the application.");
  }
  g_object_set_data_full(G_OBJECT(self->window), "ativ-state", self, ativ_window_free);
  gtk_window_present(GTK_WINDOW(self->window));
}

int main(int argc, char **argv) {
  g_autoptr(AdwApplication) application = adw_application_new("com.tlolabs.ativ", G_APPLICATION_DEFAULT_FLAGS);
  g_signal_connect(application, "activate", G_CALLBACK(activate), NULL);
  return g_application_run(G_APPLICATION(application), argc, argv);
}
