// SPDX-License-Identifier: GPL-3.0-or-later
#include "MainWindow.h"
#include "PreferencesDialog.h"
#include <QtWidgets>
#include <QMimeData>
#include <QUrl>
#include <QStyleHints>
#include <QAccessible>

class PreviewCanvas : public QWidget {
public:
    QImage image;
    explicit PreviewCanvas(QWidget *parent = nullptr) : QWidget(parent) {
        setMinimumSize(180, 180);
        setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
        setAccessibleName("Video frame preview");
        setAccessibleDescription("Preview of the composited video frame using selected artwork, aspect ratio, and flip options");
    }
    void paintEvent(QPaintEvent *) override {
        QPainter painter(this);
        painter.setRenderHint(QPainter::Antialiasing);
        painter.fillRect(rect(), palette().brush(QPalette::Base));
        if (image.isNull()) {
            painter.setPen(palette().color(QPalette::PlaceholderText));
            painter.drawText(rect().adjusted(24, 24, -24, -24), Qt::AlignCenter | Qt::TextWordWrap,
                             "Choose artwork to preview your video");
            return;
        }
        const QSize fit = image.size().scaled(size() - QSize(32, 32), Qt::KeepAspectRatio);
        const QRect frame(QPoint((width() - fit.width()) / 2, (height() - fit.height()) / 2), fit);
        painter.setRenderHint(QPainter::SmoothPixmapTransform);
        painter.drawImage(frame, image);
    }
};

QString MainWindow::resolveEnginePath(const QString &specified) {
    if (!specified.isEmpty() && QFile::exists(specified)) {
        return specified;
    }
    const QString configured = qEnvironmentVariable("ATIV_ENGINE_PATH");
    if (!configured.isEmpty() && QFile::exists(configured)) {
        return configured;
    }
#if defined(Q_OS_WIN)
    const QString standard = QCoreApplication::applicationDirPath() + "/ativ-engine.exe";
#else
    const QString standard = QCoreApplication::applicationDirPath() + "/ativ-engine";
#endif
    if (QFile::exists(standard)) {
        return standard;
    }
    return specified.isEmpty() ? standard : specified;
}

MainWindow::MainWindow(const QString &engine, QWidget *parent)
    : QMainWindow(parent),
      presetsJob(resolveEnginePath(engine), this),
      previewJob(resolveEnginePath(engine), this),
      probeJob(resolveEnginePath(engine), this),
      renderJob(resolveEnginePath(engine), this) {

#if defined(Q_OS_MACOS)
    setWindowTitle("ATIV Reference — Qt (Internal Only)");
#else
    if (Preferences::isDevelopmentBuild()) {
        setWindowTitle("ATIV Development");
    } else {
        setWindowTitle("ATIV — Artwork + Tracks Into Video");
    }
#endif

    preferences = Preferences::load();
    applyAppearance(preferences.appearance);

    resize(1020, 740);
    setMinimumSize(640, 480);
    setAcceptDrops(true);

    auto *root = new QWidget;
    auto *outer = new QVBoxLayout(root);
    outer->setContentsMargins(20, 20, 20, 16);
    outer->setSpacing(16);

    auto *title = new QLabel("Create a video");
    QFont titleFont = title->font();
    titleFont.setPointSize(24);
    titleFont.setBold(true);
    title->setFont(titleFont);
    title->setAccessibleName("Create a video heading");
    outer->addWidget(title);

    auto *subtitle = new QLabel("Combine one image with an audio recording for social media distribution.");
    subtitle->setWordWrap(true);
    outer->addWidget(subtitle);

    auto *splitter = new QSplitter;
    controls = new QWidget;
    auto *left = new QVBoxLayout(controls);
    left->setContentsMargins(0, 0, 16, 0);
    left->setSpacing(14);

    auto fileRow = [this](const QString &name, QLineEdit *&field, const QString &id, auto action) {
        auto *row = new QWidget;
        auto *layout = new QHBoxLayout(row);
        layout->setContentsMargins(0, 0, 0, 0);
        field = new QLineEdit;
        field->setReadOnly(true);
        field->setPlaceholderText("Nothing selected");
        field->setObjectName(id);
        field->setAccessibleName("Selected " + name);
        field->setMinimumWidth(120);
        auto *button = new QPushButton("Choose…");
        button->setAccessibleName("Choose " + name);
        connect(button, &QPushButton::clicked, this, action);
        layout->addWidget(field, 1);
        layout->addWidget(button);
        return row;
    };

    auto *sources = new QGroupBox("Source media");
    auto *sourceForm = new QFormLayout(sources);
    sourceForm->setFieldGrowthPolicy(QFormLayout::AllNonFixedFieldsGrow);
    sourceForm->setRowWrapPolicy(QFormLayout::WrapLongRows);
    sourceForm->setLabelAlignment(Qt::AlignLeft);
    sourceForm->addRow("Image", fileRow("image", imagePath, "imagePath", &MainWindow::chooseImage));
    sourceForm->addRow("Audio", fileRow("audio", audioPath, "audioPath", &MainWindow::chooseAudio));
    duration = new QLabel("Choose an audio recording");
    duration->setObjectName("duration");
    duration->setAccessibleName("Audio recording duration");
    sourceForm->addRow("", duration);
    left->addWidget(sources);

    auto *format = new QGroupBox("Format");
    auto *form = new QFormLayout(format);
    form->setFieldGrowthPolicy(QFormLayout::AllNonFixedFieldsGrow);
    form->setRowWrapPolicy(QFormLayout::WrapLongRows);
    form->setLabelAlignment(Qt::AlignLeft);

    platform = new QComboBox;
    platform->setObjectName("platform");
    platform->setAccessibleName("Social media outlet");

    aspect = new QComboBox;
    aspect->setObjectName("aspect");
    aspect->setAccessibleName("Aspect ratio");

    resolution = new QComboBox;
    resolution->setObjectName("resolution");
    resolution->setAccessibleName("Resolution");

    bitrate = new QComboBox;
    bitrate->addItems({"128k", "192k", "256k", "320k"});
    if (bitrate->findText(preferences.bitrate) >= 0) {
        bitrate->setCurrentText(preferences.bitrate);
    } else {
        bitrate->setCurrentText("128k");
    }
    bitrate->setAccessibleName("Audio bitrate");

    for (auto *combo : {platform, aspect, resolution, bitrate}) {
        combo->setSizeAdjustPolicy(QComboBox::AdjustToMinimumContentsLengthWithIcon);
        combo->setMinimumContentsLength(12);
        combo->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    }

    fps = new QSpinBox;
    fps->setRange(1, 240);
    fps->setValue(preferences.fps);
    fps->setSuffix(" fps");
    fps->setObjectName("fps");
    fps->setAccessibleName("Frames per second");

    form->addRow("Social media outlet", platform);
    form->addRow("Aspect ratio", aspect);
    form->addRow("Resolution", resolution);
    form->addRow("Audio bitrate", bitrate);
    form->addRow("Frame rate", fps);

    for (int i = 0; i < form->rowCount(); ++i) {
        if (auto *labelItem = form->itemAt(i, QFormLayout::LabelRole)) {
            if (auto *label = qobject_cast<QLabel *>(labelItem->widget())) {
                if (auto *fieldItem = form->itemAt(i, QFormLayout::FieldRole)) {
                    if (auto *field = fieldItem->widget()) {
                        label->setBuddy(field);
                    }
                }
            }
        }
    }
    left->addWidget(format);

    auto *flips = new QGroupBox("Image options");
    auto *flipLayout = new QHBoxLayout(flips);
    flipH = new QCheckBox("Flip horizontally");
    flipH->setObjectName("flipHorizontal");
    flipH->setAccessibleName("Flip image horizontally");
    flipV = new QCheckBox("Flip vertically");
    flipV->setObjectName("flipVertical");
    flipV->setAccessibleName("Flip image vertically");
    flipLayout->addWidget(flipH);
    flipLayout->addWidget(flipV);
    left->addWidget(flips);

    auto *destination = new QGroupBox("Destination");
    auto *destLayout = new QVBoxLayout(destination);
    destLayout->addWidget(fileRow("MP4 video destination", outputPath, "outputPath", &MainWindow::chooseOutput));
    left->addWidget(destination);
    left->addStretch();

    auto *controlsScroll = new QScrollArea;
    controlsScroll->setWidgetResizable(true);
    controlsScroll->setFrameShape(QFrame::NoFrame);
    controlsScroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    controlsScroll->setMinimumWidth(300);
    controlsScroll->setWidget(controls);
    splitter->addWidget(controlsScroll);

    auto *right = new QWidget;
    auto *rightLayout = new QVBoxLayout(right);
    rightLayout->setContentsMargins(0, 0, 0, 0);

    auto *previewTitle = new QLabel("Preview");
    QFont heading = previewTitle->font();
    heading.setBold(true);
    previewTitle->setFont(heading);
    previewTitle->setAlignment(Qt::AlignCenter);
    rightLayout->addWidget(previewTitle);

    preview = new PreviewCanvas;
    rightLayout->addWidget(preview, 1);

    previewCaption = new QLabel("Choose an image to see a styled preview.");
    previewCaption->setObjectName("previewCaption");
    previewCaption->setAlignment(Qt::AlignCenter);
    previewCaption->setWordWrap(true);
    rightLayout->addWidget(previewCaption);

    auto *diagnosticToggle = new QCheckBox("Show diagnostics");
    rightLayout->addWidget(diagnosticToggle);

    diagnostics = new QPlainTextEdit;
    diagnostics->setReadOnly(true);
    diagnostics->setMaximumBlockCount(250);
    diagnostics->setMaximumHeight(110);
    diagnostics->hide();
    connect(diagnosticToggle, &QCheckBox::toggled, diagnostics, &QWidget::setVisible);
    rightLayout->addWidget(diagnostics);

    splitter->addWidget(right);
    splitter->setSizes({490, 450});
    outer->addWidget(splitter, 1);

    progress = new QProgressBar;
    progress->setRange(0, 1000);
    progress->setValue(0);
    progress->setFormat("%p% complete");
    progress->setAccessibleName("Video creation progress");
    outer->addWidget(progress);

    auto *footer = new QHBoxLayout;
    status = new QLabel("Loading formats…");
    status->setWordWrap(true);
    status->setObjectName("status");
    // The current message is the accessible name of a QLabel. A fixed name
    // would hide the actual status from screen readers.
    footer->addWidget(status, 1);

#if defined(Q_OS_MACOS)
    reveal = new QPushButton("Show in Finder");
#else
    reveal = new QPushButton("Show in Folder");
#endif
    reveal->hide();
    reveal->setAccessibleName("Reveal exported video file");
    footer->addWidget(reveal);

    create = new QPushButton("Create Video");
    create->setObjectName("createVideo");
    create->setDefault(true);
    create->setShortcut(QKeySequence(Qt::CTRL | Qt::Key_Return));
    create->setAccessibleName("Create video");
    create->setAccessibleDescription("Start combining artwork and audio into video");
    footer->addWidget(create);

    cancel = new QPushButton("Stop Video Creation");
    cancel->setObjectName("cancelRender");
    cancel->setShortcut(QKeySequence(Qt::Key_Escape));
    cancel->setAccessibleName("Stop video creation");
    cancel->setAccessibleDescription("Safely cancel video export and preserve previous file");
    cancel->hide();
    footer->addWidget(cancel);

    outer->addLayout(footer);
    setCentralWidget(root);

    connect(create, &QPushButton::clicked, this, &MainWindow::startRender);
    connect(cancel, &QPushButton::clicked, this, &MainWindow::cancelRender);
    connect(reveal, &QPushButton::clicked, this, [this] {
        if (completedOutput.isEmpty()) return;
#if defined(Q_OS_MACOS)
        QProcess::startDetached("/usr/bin/open", {"-R", completedOutput});
#elif defined(Q_OS_WIN)
        QProcess::startDetached("explorer.exe", {"/select,", QDir::toNativeSeparators(completedOutput)});
#else
        QDesktopServices::openUrl(QUrl::fromLocalFile(QFileInfo(completedOutput).absolutePath()));
#endif
    });

    auto *fileMenu = menuBar()->addMenu("File");
    auto *chooseImgAct = fileMenu->addAction("Choose Image…", QKeySequence("Ctrl+I"), this, &MainWindow::chooseImage);
    chooseImgAct->setShortcutVisibleInContextMenu(true);
    auto *chooseAudAct = fileMenu->addAction("Choose Audio…", QKeySequence("Ctrl+O"), this, &MainWindow::chooseAudio);
    chooseAudAct->setShortcutVisibleInContextMenu(true);
    auto *chooseOutAct = fileMenu->addAction("Choose Destination…", QKeySequence("Ctrl+Shift+S"), this, &MainWindow::chooseOutput);
    chooseOutAct->setShortcutVisibleInContextMenu(true);
    fileMenu->addSeparator();
    fileMenu->addAction("Close", QKeySequence::Close, this, &QWidget::close);

    auto *settingsMenu = menuBar()->addMenu("Settings");
    settingsMenu->addAction("Preferences…", this, &MainWindow::showPreferences);

    auto *helpMenu = menuBar()->addMenu("Help");
    checkUpdatesAction = helpMenu->addAction("Check for Updates…", this, [this] { checkForUpdates(true); });
    checkUpdatesAction->setEnabled(UpdateClient::isSupported());
    helpMenu->addSeparator();
    helpMenu->addAction("About ATIV", this, &MainWindow::showAbout);
    helpMenu->addAction("About Qt", qApp, &QApplication::aboutQt);

    connect(platform, &QComboBox::currentIndexChanged, this, &MainWindow::updateAspects);
    connect(aspect, &QComboBox::currentIndexChanged, this, &MainWindow::updateResolutions);
    connect(resolution, &QComboBox::currentIndexChanged, this, &MainWindow::queuePreview);
    connect(flipH, &QCheckBox::toggled, this, &MainWindow::queuePreview);
    connect(flipV, &QCheckBox::toggled, this, &MainWindow::queuePreview);

    previewDelay.setSingleShot(true);
    previewDelay.setInterval(180);
    connect(&previewDelay, &QTimer::timeout, this, &MainWindow::startPreview);

    connect(&presetsJob, &EngineJob::eventReceived, this, [this](const QJsonObject &event) {
        if (event["event"] != "presets") return;
        presets = event["items"].toArray();
        QSignalBlocker blocker(platform);
        for (const auto &value : presets) {
            const auto name = value.toObject()["platform"].toString();
            if (platform->findText(name) < 0) platform->addItem(name);
        }
    });

    connect(&presetsJob, &EngineJob::finished, this, [this](int code, const QString &error) {
        presetsLoaded = (code == 0 && !presets.isEmpty());
        if (presetsLoaded) {
            updateAspects();
            setStatus("Choose an image, audio, and a destination to begin.", true);
            emit presetsReady(presets.size());

            const QString smokeReport = qEnvironmentVariable("ATIV_SMOKE_REPORT");
            if (!smokeReport.isEmpty() && presets.size() == 27) {
                QFile file(smokeReport);
                if (file.open(QIODevice::WriteOnly | QIODevice::Truncate | QIODevice::Text)) {
                    file.write("{\"startup\":true,\"presets\":27}\n");
                    file.flush();
                }
            }
        } else {
            setStatus(error.isEmpty() ? "No format presets were returned." : error, true);
            log(status->text());
        }
        updateEnabled();
    });

    connect(&previewJob, &EngineJob::finished, this, [this](int code, const QString &error) {
        if (closing) { close(); return; }
        if (previewRevision != revision) { previewDelay.start(); return; }
        if (code == 0) {
            preview->image = QImage(temporary.filePath("preview.png"));
            preview->update();
            if (!preview->image.isNull()) {
                previewCaption->setText("Preview ready · " + aspect->currentText() + " · " + resolution->currentText());
                emit previewReady(preview->image);
            }
            else previewCaption->setText("The preview could not be read.");
        } else {
            previewCaption->setText("Preview unavailable. Check the selected image.");
            log(error);
        }
    });

    connect(&probeJob, &EngineJob::eventReceived, this, [this](const QJsonObject &event) {
        if (probedPath != audioPath->text() || event["event"] != "probe") return;
        const auto value = event["duration_seconds"];
        if (value.isDouble()) {
            const int seconds = qRound(value.toDouble());
            if (seconds >= 3600) {
                duration->setText(QString("%1:%2:%3")
                    .arg(seconds / 3600)
                    .arg((seconds % 3600) / 60, 2, 10, QChar('0'))
                    .arg(seconds % 60, 2, 10, QChar('0')));
            } else {
                duration->setText(QString("%1:%2")
                    .arg(seconds / 60, 2, 10, QChar('0'))
                    .arg(seconds % 60, 2, 10, QChar('0')));
            }
        } else {
            duration->setText("Duration unavailable");
        }
    });

    connect(&probeJob, &EngineJob::finished, this, [this](int code, const QString &error) {
        if (closing) { close(); return; }
        if (probedPath != audioPath->text()) { beginProbe(); return; }
        if (code != 0) { duration->setText("Could not read audio"); log(error); }
    });

    connect(&renderJob, &EngineJob::eventReceived, this, [this](const QJsonObject &event) {
        const auto type = event["event"].toString();
        if (type == "stage") {
            const auto stage = event["stage"].toString();
            log(stage);
            if (cancel->isEnabled()) {
                if (stage == "validating") setStatus("Checking files…", true);
                else if (stage == "probing") setStatus("Reading media…", true);
                else if (stage == "compositing") setStatus("Building frame…", true);
                else if (stage == "encoding") setStatus("Creating video…", true);
                else if (stage == "publishing") setStatus("Saving completed video…", true);
                else if (stage == "complete") setStatus("Complete", true);
                else setStatus(stage, true);
            }
        }
        if (type == "progress") {
            if (event["fraction"].isDouble()) {
                progress->setRange(0, 1000);
                progress->setValue(qBound(0, qRound(event["fraction"].toDouble() * 1000), 1000));
            }
            if (cancel->isEnabled()) {
                QString text = "Creating video…";
                if (event["fraction"].isDouble()) {
                    text += QString(" %1%").arg(qRound(event["fraction"].toDouble() * 100));
                }
                if (event["eta_seconds"].isDouble()) {
                    const int eta = qRound(event["eta_seconds"].toDouble());
                    text += QString(" · about %1:%2 remaining")
                        .arg(eta / 60)
                        .arg(eta % 60, 2, 10, QChar('0'));
                }
                status->setText(text);
            }
        }
    });

    connect(&renderJob, &EngineJob::finished, this, [this](int code, const QString &error) {
        rendering = false;
        progress->setRange(0, 1000);
        progress->setValue(code == 0 ? 1000 : 0);
        if (code == 0) {
            completedOutput = outputPath->text();
            setStatus(QString("Video saved as %1.").arg(QFileInfo(completedOutput).fileName()), true);
            reveal->show();
        } else if (code == 130) {
            setStatus("Video creation stopped. Previous output preserved.", true);
        } else {
            setStatus(error, true);
            log(error);
        }
        updateEnabled();
        emit renderFinished(code);
        if (closing) close();
    });

    updateEnabled();
    QTimer::singleShot(0, this, [this] { presetsJob.start({"presets"}); });

    if (UpdateClient::isSupported()) {
        updateTimer.setInterval(24 * 60 * 60 * 1000);
        connect(&updateTimer, &QTimer::timeout, this, [this] {
            if (preferences.automaticUpdates && !rendering && !updating) {
                checkForUpdates(false);
            }
        });
        updateTimer.start();

        if (preferences.automaticUpdates) {
            QTimer::singleShot(3000, this, [this] {
                if (preferences.automaticUpdates && !rendering && !updating) {
                    checkForUpdates(false);
                }
            });
        }
    }
}

void MainWindow::log(const QString &message) {
    if (diagnostics) diagnostics->appendPlainText(message);
}

void MainWindow::setStatus(const QString &message, bool announce) {
    if (status->text() == message) return;
    status->setText(message);
    if (announce) {
        QAccessibleEvent changed(status, QAccessible::NameChanged);
        QAccessible::updateAccessibility(&changed);
    }
}

void MainWindow::suggestOutput(const QString &sourcePath) {
    if (!outputPath->text().trimmed().isEmpty() || sourcePath.trimmed().isEmpty()) return;
    QFileInfo info(sourcePath);
    QString suggested;
    if (info.suffix().compare("mp4", Qt::CaseInsensitive) == 0) {
        suggested = info.dir().filePath(info.completeBaseName() + "-video.mp4");
    } else {
        suggested = info.dir().filePath(info.completeBaseName() + ".mp4");
    }
    outputPath->setText(suggested);
    outputPath->setToolTip(suggested);
}

void MainWindow::setImage(const QString &path) {
    if (rendering || updating || path.isEmpty()) return;
    imagePath->setText(path);
    imagePath->setToolTip(path);
    suggestOutput(path);
    queuePreview();
    updateEnabled();
}

void MainWindow::setAudio(const QString &path) {
    if (rendering || updating || path.isEmpty()) return;
    audioPath->setText(path);
    audioPath->setToolTip(path);
    duration->setText("Reading duration…");
    suggestOutput(path);
    if (probeJob.busy()) probeJob.cancel();
    else beginProbe();
    updateEnabled();
}

void MainWindow::setOutput(const QString &path) {
    if (rendering || updating) return;
    outputPath->setText(path);
    outputPath->setToolTip(path);
    reveal->hide();
    updateEnabled();
}

void MainWindow::chooseImage() {
    if (rendering || updating) return;
    setImage(QFileDialog::getOpenFileName(this, "Choose Image", {},
        "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.ppm);;All files (*)"));
}

void MainWindow::chooseAudio() {
    if (rendering || updating) return;
    setAudio(QFileDialog::getOpenFileName(this, "Choose Audio", {},
        "Audio (*.wav *.mp3 *.m4a *.m4b *.aac *.flac *.ogg *.oga *.opus *.aif *.aiff *.wma *.alac);;All files (*)"));
}

void MainWindow::chooseOutput() {
    if (rendering || updating) return;
    QString defaultName = outputPath->text().isEmpty() ? (QDir::homePath() + "/Movies/Untitled.mp4") : outputPath->text();
    QString path = QFileDialog::getSaveFileName(this, "Save Video", defaultName,
        "MP4 video (*.mp4)", nullptr, QFileDialog::DontConfirmOverwrite);
    if (!path.isEmpty() && !path.endsWith(".mp4", Qt::CaseInsensitive)) {
        path += ".mp4";
    }
    if (!path.isEmpty()) {
        setOutput(path);
    }
}

void MainWindow::updateAspects() {
    const QSignalBlocker blocker(aspect);
    aspect->clear();
    for (const auto &value : presets) {
        const auto p = value.toObject();
        if (p["platform"] == platform->currentText() && aspect->findText(p["aspect"].toString()) < 0) {
            aspect->addItem(p["aspect"].toString());
        }
    }
    updateResolutions();
}

void MainWindow::updateResolutions() {
    const QSignalBlocker blocker(resolution);
    resolution->clear();
    for (const auto &value : presets) {
        const auto p = value.toObject();
        if (p["platform"] == platform->currentText() && p["aspect"] == aspect->currentText()) {
            resolution->addItem(QString("%1 × %2").arg(p["width"].toInt()).arg(p["height"].toInt()), p);
        }
    }
    queuePreview();
    updateEnabled();
}

QStringList MainWindow::compositionArguments(bool forExport) const {
    const auto p = resolution->currentData().toJsonObject();
    const int origW = p["width"].toInt();
    const int origH = p["height"].toInt();

    int w = origW;
    int h = origH;
    if (!forExport && origW > 0 && origH > 0) {
        const double ratio = double(origW) / double(origH);
        w = ratio >= 1.0 ? 360 : qMax(2, int(360.0 * ratio) & ~1);
        h = ratio >= 1.0 ? qMax(2, int(360.0 / ratio) & ~1) : 360;
    }

    QStringList args{"--image", imagePath->text(), "--width", QString::number(w), "--height", QString::number(h)};
    if (flipH->isChecked()) args << "--flip-horizontal";
    if (flipV->isChecked()) args << "--flip-vertical";
    return args;
}

void MainWindow::queuePreview() {
    ++revision;
    preview->image = QImage();
    preview->update();
    previewCaption->setText(imagePath->text().isEmpty()
        ? "Choose an image to see a styled preview."
        : "Preparing preview · " + aspect->currentText() + " · " + resolution->currentText());
    if (previewJob.busy()) previewJob.cancel();
    previewDelay.start();
}

void MainWindow::startPreview() {
    if (closing || previewJob.busy() || imagePath->text().isEmpty() || resolution->currentIndex() < 0) return;
    if (!temporary.isValid()) {
        previewCaption->setText("Could not create a preview folder.");
        return;
    }
    previewRevision = revision;
    previewJob.start(QStringList{"preview", "--output", temporary.filePath("preview.png")} + compositionArguments(false));
}

void MainWindow::beginProbe() {
    probedPath = audioPath->text();
    if (!probedPath.isEmpty()) {
        probeJob.start({"probe", "--audio", probedPath});
    }
}

void MainWindow::updateEnabled() {
    controls->setEnabled(!rendering && !updating);
    create->setVisible(!rendering);
    cancel->setVisible(rendering);
    cancel->setEnabled(rendering);

    const QString img = imagePath ? imagePath->text().trimmed() : QString();
    const QString aud = audioPath ? audioPath->text().trimmed() : QString();
    const QString out = outputPath ? outputPath->text().trimmed() : QString();

    const bool pathsDistinct = !out.isEmpty() &&
        out.compare(img, Qt::CaseInsensitive) != 0 &&
        out.compare(aud, Qt::CaseInsensitive) != 0;

    const bool canRender = presetsLoaded && resolution && resolution->currentIndex() >= 0 &&
                           !img.isEmpty() && !aud.isEmpty() && pathsDistinct &&
                           !rendering && !updating;
    create->setEnabled(canRender);
}

void MainWindow::startRender() {
    if (!create->isEnabled() || rendering) return;
    if (QFileInfo::exists(outputPath->text()) &&
        QMessageBox::question(this, "Replace Video?", "Replace the existing destination after this export succeeds?",
                              QMessageBox::Yes | QMessageBox::No, QMessageBox::No) != QMessageBox::Yes) {
        return;
    }
    rendering = true;
    reveal->hide();
    progress->setRange(0, 0);
    setStatus("Preparing video…", true);
    updateEnabled();

    preferences.save();

    renderJob.start(QStringList{"render", "--audio", audioPath->text(), "--output", outputPath->text(),
                                "--fps", QString::number(fps->value()), "--audio-bitrate", bitrate->currentText()}
                    + compositionArguments(true));
}

void MainWindow::cancelRender() {
    if (!rendering) return;
    cancel->setEnabled(false);
    setStatus("Stopping safely…", true);
    renderJob.cancel();
}

void MainWindow::closeEvent(QCloseEvent *event) {
    if (rendering && !closing) {
        if (QMessageBox::question(this, "Stop Video Creation?", "Stop the current export and close ATIV?",
                                  QMessageBox::Yes | QMessageBox::No, QMessageBox::No) != QMessageBox::Yes) {
            event->ignore();
            return;
        }
        closing = true;
        cancelRender();
    }
    closing = true;
    updateTimer.stop();
    previewDelay.stop();
    previewJob.cancel();
    probeJob.cancel();
    preferences.save();

    if (renderJob.busy() || previewJob.busy() || probeJob.busy() || presetsJob.busy()) {
        event->ignore();
        QTimer::singleShot(100, this, &QWidget::close);
        return;
    }
    event->accept();
}

void MainWindow::dragEnterEvent(QDragEnterEvent *event) {
    if (!rendering && !updating && event->mimeData()->hasUrls()) {
        event->acceptProposedAction();
    }
}

void MainWindow::dropEvent(QDropEvent *event) {
    if (rendering || updating) return;
    const QStringList audioExtensions{"wav", "mp3", "m4a", "m4b", "aac", "flac", "ogg", "oga", "opus", "aif", "aiff", "wma", "alac"};
    for (const auto &url : event->mimeData()->urls()) {
        if (url.isLocalFile()) {
            const auto path = url.toLocalFile();
            const auto ext = QFileInfo(path).suffix().toLower();
            if (audioExtensions.contains(ext)) {
                setAudio(path);
            } else {
                setImage(path);
            }
        }
    }
    event->acceptProposedAction();
}

void MainWindow::showPreferences() {
    PreferencesDialog dialog(preferences, this);
    if (dialog.exec() == QDialog::Accepted) {
        preferences = dialog.preferences();
        preferences.save();
        applyAppearance(preferences.appearance);
        if (!rendering) {
            if (bitrate->findText(preferences.bitrate) >= 0) {
                bitrate->setCurrentText(preferences.bitrate);
            }
            fps->setValue(preferences.fps);
        }
    }
}

void MainWindow::showAbout() {
    QMessageBox::about(this, "About ATIV",
        QString("ATIV %1\n\nArtwork + Tracks Into Video\nLocal media processing. No telemetry.\n\nA TLO Labs project · GPL-3.0-or-later\nQt %2 Widgets + ATIV Rust engine")
            .arg(QCoreApplication::applicationVersion(), QT_VERSION_STR));
}

void MainWindow::applyAppearance(const QString &theme) {
    if (theme == "Dark") {
        qApp->styleHints()->setColorScheme(Qt::ColorScheme::Dark);
        QPalette dark;
        dark.setColor(QPalette::Window, QColor(40, 42, 48));
        dark.setColor(QPalette::WindowText, Qt::white);
        dark.setColor(QPalette::Base, QColor(25, 26, 30));
        dark.setColor(QPalette::AlternateBase, QColor(40, 42, 48));
        dark.setColor(QPalette::ToolTipBase, QColor(48, 50, 56));
        dark.setColor(QPalette::ToolTipText, Qt::white);
        dark.setColor(QPalette::Text, Qt::white);
        dark.setColor(QPalette::Button, QColor(48, 50, 56));
        dark.setColor(QPalette::ButtonText, Qt::white);
        dark.setColor(QPalette::BrightText, Qt::red);
        dark.setColor(QPalette::Link, QColor(64, 150, 238));
        dark.setColor(QPalette::Highlight, QColor(64, 150, 238));
        dark.setColor(QPalette::HighlightedText, Qt::black);
        dark.setColor(QPalette::PlaceholderText, QColor(160, 160, 160));
        const QColor disabledText(170, 170, 170);
        for (const auto role : {QPalette::WindowText, QPalette::Text, QPalette::ButtonText}) {
            dark.setColor(QPalette::Disabled, role, disabledText);
        }
        qApp->setPalette(dark);
    } else if (theme == "Light") {
        qApp->styleHints()->setColorScheme(Qt::ColorScheme::Light);
        qApp->setPalette(qApp->style()->standardPalette());
    } else {
        qApp->styleHints()->setColorScheme(Qt::ColorScheme::Unknown);
        qApp->setPalette(qApp->style()->standardPalette());
    }
}

void MainWindow::checkForUpdates(bool manual) {
    if (!UpdateClient::isSupported()) return;
    if (rendering || updating) return;

    updating = true;
    updateEnabled();
    if (manual) {
        status->setText("Checking for updates…");
    }

    updateClient.checkForUpdates(manual, [this, manual](bool available, const QString &ver, const QString &err) {
        updating = false;
        updateEnabled();

        if (!err.isEmpty()) {
            if (manual) {
                QMessageBox::warning(this, "Update Error", err);
                status->setText(err);
            }
            return;
        }

        if (!available) {
            if (manual) {
                QMessageBox::information(this, "ATIV is up to date", "No newer build is available for this platform.");
                status->setText("ATIV is up to date.");
            }
            return;
        }

        const QString prompt = QString("ATIV %1 is available.\n\nDownload and install the verified update?").arg(ver);
        if (QMessageBox::question(this, "Update Available", prompt, QMessageBox::Yes | QMessageBox::No, QMessageBox::Yes) == QMessageBox::Yes) {
            updating = true;
            updateEnabled();
            status->setText("Downloading update…");
            updateClient.installOrDownload(this, [this](bool success, const QString &msg) {
                updating = false;
                updateEnabled();
                if (success) {
                    QMessageBox::information(this, "Update", msg);
                } else {
                    QMessageBox::warning(this, "Update Failed", msg);
                }
                status->setText(msg);
            });
        }
    });
}
