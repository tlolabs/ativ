// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "EngineJob.h"
#include "Preferences.h"
#include "UpdateClient.h"
#include <QMainWindow>
#include <QJsonArray>
#include <QTemporaryDir>
#include <QTimer>

class QLineEdit;
class QComboBox;
class QSpinBox;
class QCheckBox;
class QLabel;
class QPushButton;
class QProgressBar;
class QPlainTextEdit;
class PreviewCanvas;

class MainWindow : public QMainWindow {
    Q_OBJECT
public:
    explicit MainWindow(const QString &engine = QString(), QWidget *parent = nullptr);
    void setImage(const QString &path);
    void setAudio(const QString &path);
    void setOutput(const QString &path);
    void startRender();
    void cancelRender();

    Preferences currentPreferences() const { return preferences; }
    void applyAppearance(const QString &theme);

signals:
    void presetsReady(int count);
    void previewReady(const QImage &image);
    void renderFinished(int code);

protected:
    void closeEvent(QCloseEvent *event) override;
    void dragEnterEvent(QDragEnterEvent *event) override;
    void dropEvent(QDropEvent *event) override;

private:
    void chooseImage();
    void chooseAudio();
    void chooseOutput();
    void updateAspects();
    void updateResolutions();
    void queuePreview();
    void startPreview();
    void updateEnabled();
    void beginProbe();
    QStringList compositionArguments(bool forExport = false) const;
    void log(const QString &message);
    void setStatus(const QString &message, bool announce = false);
    void suggestOutput(const QString &sourcePath);
    void showPreferences();
    void showAbout();
    void checkForUpdates(bool manual);

    static QString resolveEnginePath(const QString &specified);

    Preferences preferences;
    UpdateClient updateClient;
    QTimer updateTimer;

    EngineJob presetsJob, previewJob, probeJob, renderJob;
    QTemporaryDir temporary;
    QTimer previewDelay;
    QJsonArray presets;
    QLineEdit *imagePath = nullptr;
    QLineEdit *audioPath = nullptr;
    QLineEdit *outputPath = nullptr;
    QComboBox *platform = nullptr;
    QComboBox *aspect = nullptr;
    QComboBox *resolution = nullptr;
    QComboBox *bitrate = nullptr;
    QSpinBox *fps = nullptr;
    QCheckBox *flipH = nullptr;
    QCheckBox *flipV = nullptr;
    QLabel *status = nullptr;
    QLabel *duration = nullptr;
    QLabel *previewCaption = nullptr;
    PreviewCanvas *preview = nullptr;
    QPushButton *create = nullptr;
    QPushButton *cancel = nullptr;
    QPushButton *reveal = nullptr;
    QProgressBar *progress = nullptr;
    QPlainTextEdit *diagnostics = nullptr;
    QWidget *controls = nullptr;
    QAction *checkUpdatesAction = nullptr;
    QString probedPath, completedOutput;
    int revision = 0, previewRevision = -1;
    bool rendering = false, closing = false, presetsLoaded = false, updating = false;
};
