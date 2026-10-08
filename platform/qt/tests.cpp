// SPDX-License-Identifier: GPL-3.0-or-later
#include "MainWindow.h"
#include "Preferences.h"
#include "UpdateClient.h"
#include <QtTest>
#include <QtWidgets>
#include <QJsonDocument>

class WorkflowTests : public QObject {
    Q_OBJECT
    QString engine, image, audio;
    QTemporaryDir media;
    static QByteArray contents(const QString &path) { QFile f(path); if (!f.open(QIODevice::ReadOnly)) return {}; return f.readAll(); }
    static void writeWav(const QString &path, int seconds) {
        QFile file(path); QVERIFY(file.open(QIODevice::WriteOnly));
        QDataStream stream(&file); stream.setByteOrder(QDataStream::LittleEndian);
        stream.writeRawData("RIFF", 4); stream << quint32(36 + seconds*16000); stream.writeRawData("WAVEfmt ", 8);
        stream << quint32(16) << quint16(1) << quint16(1) << quint32(8000) << quint32(16000) << quint16(2) << quint16(16);
        stream.writeRawData("data", 4); stream << quint32(seconds*16000);
        const QByteArray samples(seconds*16000, '\0'); stream.writeRawData(samples.constData(), samples.size());
    }
private slots:
    void initTestCase() {
        engine = qEnvironmentVariable("ATIV_QT_TEST_ENGINE");
        QVERIFY2(QFileInfo::exists(engine), "Set ATIV_QT_TEST_ENGINE to the packaged engine");
        QVERIFY(media.isValid());
        image = media.filePath("artwork ü.png"); audio = media.filePath("audio ü.wav");
        QImage artwork(96, 64, QImage::Format_RGB32);
        for (int y=0; y<64; ++y) for (int x=0; x<96; ++x) artwork.setPixelColor(x,y,x<48 ? QColor(230,40,30) : QColor(20,80,220));
        QVERIFY(artwork.save(image)); writeWav(audio, 2);
    }
    void missingEngine() {
        EngineJob job(media.filePath("missing-engine")); QSignalSpy done(&job, &EngineJob::finished);
        job.start({"presets"}); QTRY_COMPARE_WITH_TIMEOUT(done.size(), 1, 5000);
        QCOMPARE(done[0][0].toInt(), -1); QVERIFY(!done[0][1].toString().isEmpty()); QVERIFY(!job.busy());
    }
    void preferencesAndLegacyMigration() {
        const QString iniPath = media.filePath("legacy-preferences.ini");
        QFile iniFile(iniPath);
        QVERIFY(iniFile.open(QIODevice::WriteOnly | QIODevice::Text));
        iniFile.write("[General]\nappearance=dark\nbitrate=192k\nfps=60\nautomatic_updates=false\n");
        iniFile.close();

        const auto migrated = Preferences::loadLegacyLinux(iniPath);
        QCOMPARE(migrated.appearance, QString("Dark"));
        QCOMPARE(migrated.bitrate, QString("192k"));
        QCOMPARE(migrated.fps, 60);
        QCOMPARE(migrated.automaticUpdates, false);

        Preferences prefs;
        prefs.appearance = "Light";
        prefs.bitrate = "320k";
        prefs.fps = 120;
        prefs.automaticUpdates = true;
        QVERIFY(prefs.save());

        const auto loaded = Preferences::load();
        QCOMPARE(loaded.appearance, QString("Light"));
        QCOMPARE(loaded.bitrate, QString("320k"));
        QCOMPARE(loaded.fps, 120);
        QCOMPARE(loaded.automaticUpdates, true);
    }
    void previewAndPresetWorkflow() {
        MainWindow window(engine); QSignalSpy ready(&window, &MainWindow::presetsReady);
        QSignalSpy preview(&window, &MainWindow::previewReady);
        window.show(); QTRY_COMPARE_WITH_TIMEOUT(ready.size(), 1, 10000); QCOMPARE(ready[0][0].toInt(), 27);
        int count = 0;
        auto *outlet = window.findChild<QComboBox *>("platform"); auto *aspect = window.findChild<QComboBox *>("aspect");
        auto *resolution = window.findChild<QComboBox *>("resolution");
        for (int p=0; p<outlet->count(); ++p) { outlet->setCurrentIndex(p); for (int a=0; a<aspect->count(); ++a) { aspect->setCurrentIndex(a); count += resolution->count(); } }
        QCOMPARE(count, 27); outlet->setCurrentIndex(0); aspect->setCurrentIndex(0); resolution->setCurrentIndex(0);
        QVERIFY(!window.findChild<QPushButton *>("createVideo")->isEnabled());
        window.setImage(image); QTRY_VERIFY_WITH_TIMEOUT(preview.size() >= 1, 30000);
        const auto original = qvariant_cast<QImage>(preview.last()[0]); QVERIFY(!original.isNull());
        preview.clear(); auto *flip = window.findChild<QCheckBox *>("flipHorizontal"); flip->setChecked(true);
        QTRY_VERIFY_WITH_TIMEOUT(preview.size() >= 1, 30000);
        const auto flipped = qvariant_cast<QImage>(preview.last()[0]); QCOMPARE(original.size(), flipped.size());
        const int y=original.height()/2, x=original.width()/4;
        QVERIFY(original.pixelColor(x,y).red() > original.pixelColor(x,y).blue());
        QVERIFY(flipped.pixelColor(x,y).blue() > flipped.pixelColor(x,y).red());
        // Rapidly superseded preview requests must settle on the last selection.
        preview.clear(); flip->setChecked(false); flip->setChecked(true); flip->setChecked(false);
        QTRY_VERIFY_WITH_TIMEOUT(preview.size() >= 1, 30000);
        QVERIFY(qvariant_cast<QImage>(preview.last()[0]).pixelColor(x,y).red() > 150);
        window.close(); QTRY_VERIFY_WITH_TIMEOUT(!window.isVisible(), 10000);
    }
    void pathValidationAndOutputSuggestion() {
        MainWindow window(engine); QSignalSpy ready(&window, &MainWindow::presetsReady);
        window.show(); QTRY_COMPARE_WITH_TIMEOUT(ready.size(), 1, 10000);
        auto *outputPathEdit = window.findChild<QLineEdit *>("outputPath");
        auto *createBtn = window.findChild<QPushButton *>("createVideo");
        QVERIFY(outputPathEdit->text().isEmpty());

        window.setImage(image);
        QVERIFY(!outputPathEdit->text().isEmpty());
        QVERIFY(outputPathEdit->text().endsWith(".mp4", Qt::CaseInsensitive));
        QVERIFY(!createBtn->isEnabled()); // Audio missing

        window.setAudio(audio);
        QTRY_VERIFY(createBtn->isEnabled());

        // Reject setting output equal to image or audio
        window.setOutput(image);
        QVERIFY(!createBtn->isEnabled());

        window.setOutput(audio);
        QVERIFY(!createBtn->isEnabled());

        window.setOutput(media.filePath("valid.mp4"));
        QVERIFY(createBtn->isEnabled());

        window.close(); QTRY_VERIFY_WITH_TIMEOUT(!window.isVisible(), 10000);
    }
    void disclosureSections() {
        MainWindow window(engine);
        window.show();
        auto *source = window.findChild<QToolButton *>("sourceMediaDisclosure");
        auto *format = window.findChild<QToolButton *>("formatDisclosure");
        auto *destination = window.findChild<QToolButton *>("destinationDisclosure");
        auto *sourceSummary = window.findChild<QLabel *>("sourceMediaDisclosureSummary");
        auto *destinationSummary = window.findChild<QLabel *>("destinationDisclosureSummary");
        auto *createButton = window.findChild<QPushButton *>("createVideo");
        QVERIFY(source && format && destination && sourceSummary && destinationSummary && createButton);
        QVERIFY(source->isChecked());
        QVERIFY(!format->isChecked());
        QVERIFY(!destination->isChecked());
        QVERIFY(createButton->isVisible());

        source->click();
        QVERIFY(sourceSummary->isVisible());
        QVERIFY(!window.findChild<QLineEdit *>("imagePath")->isVisible());
        window.setImage(image);
        QVERIFY(sourceSummary->text().contains(QFileInfo(image).fileName()));
        source->click();
        QVERIFY(window.findChild<QLineEdit *>("imagePath")->isVisible());

        format->click();
        QVERIFY(window.findChild<QComboBox *>("platform")->isVisible());
        destination->click();
        QVERIFY(window.findChild<QLineEdit *>("outputPath")->isVisible());
        destination->click();
        QVERIFY(destinationSummary->isVisible());
        QVERIFY(destinationSummary->text().endsWith(".mp4"));
        QVERIFY(createButton->isVisible());
        window.close();
    }
    void exportThroughWindow() {
        MainWindow window(engine); QSignalSpy ready(&window, &MainWindow::presetsReady);
        QSignalSpy done(&window, &MainWindow::renderFinished);
        window.show(); QTRY_COMPARE_WITH_TIMEOUT(ready.size(), 1, 10000);
        const QString output = media.filePath("video ü.mp4"); const auto beforeImage = contents(image), beforeAudio = contents(audio);
        window.setImage(image); window.setAudio(audio); window.setOutput(output);
        auto *create = window.findChild<QPushButton *>("createVideo"); QVERIFY(create->isEnabled()); create->click();
        QVERIFY(!create->isEnabled()); QTRY_COMPARE_WITH_TIMEOUT(done.size(), 1, 60000); QCOMPARE(done[0][0].toInt(), 0);
        QVERIFY(QFileInfo(output).size() > 100); QCOMPARE(contents(image), beforeImage); QCOMPARE(contents(audio), beforeAudio);
        QProcess probe; probe.start(QFileInfo(engine).absolutePath()+"/ffprobe", {"-v", "error", "-show_streams", "-of", "json", output});
        QVERIFY(probe.waitForFinished(10000)); QCOMPARE(probe.exitCode(), 0);
        const auto streams = QJsonDocument::fromJson(probe.readAllStandardOutput()).object()["streams"].toArray();
        QStringList codecs; for (const auto &s : streams) codecs << s.toObject()["codec_name"].toString();
        QVERIFY(codecs.contains("h264")); QVERIFY(codecs.contains("aac"));
        QVERIFY(create->isEnabled()); window.close(); QTRY_VERIFY_WITH_TIMEOUT(!window.isVisible(), 10000);
    }
    void invalidInputThroughWindow() {
        MainWindow window(engine); QSignalSpy ready(&window, &MainWindow::presetsReady), done(&window, &MainWindow::renderFinished);
        window.show(); QTRY_COMPARE_WITH_TIMEOUT(ready.size(), 1, 10000);
        window.setImage(media.filePath("does not exist.png")); window.setAudio(audio); window.setOutput(media.filePath("failed.mp4"));
        window.startRender(); QTRY_COMPARE_WITH_TIMEOUT(done.size(), 1, 30000); QVERIFY(done[0][0].toInt() != 0);
        QVERIFY(!QFileInfo::exists(media.filePath("failed.mp4"))); QVERIFY(!window.findChild<QLabel *>("status")->text().isEmpty());
        QVERIFY(window.findChild<QPushButton *>("createVideo")->isEnabled()); window.close(); QTRY_VERIFY_WITH_TIMEOUT(!window.isVisible(), 10000);
    }
    void cancellationThroughWindow() {
        MainWindow window(engine); QSignalSpy ready(&window, &MainWindow::presetsReady), done(&window, &MainWindow::renderFinished);
        window.show(); QTRY_COMPARE_WITH_TIMEOUT(ready.size(), 1, 10000);
        const auto output = media.filePath("cancelled.mp4");
        window.setImage(image); window.setAudio(audio); window.setOutput(output);
        window.findChild<QPushButton *>("createVideo")->click();
        auto *stop = window.findChild<QPushButton *>("cancelRender"); QVERIFY(stop->isVisible()); stop->click();
        QVERIFY(!stop->isEnabled());
        QTRY_COMPARE_WITH_TIMEOUT(done.size(), 1, 30000); QCOMPARE(done[0][0].toInt(), 130);
        QVERIFY(!QFileInfo::exists(output)); QVERIFY(window.findChild<QPushButton *>("createVideo")->isEnabled());
        window.close(); QTRY_VERIFY_WITH_TIMEOUT(!window.isVisible(), 10000);
    }
    void cancellationPreservesDestination() {
        const auto longAudio = media.filePath("long track.wav"), output = media.filePath("existing.mp4");
        writeWav(longAudio, 180);
        QFile existing(output); QVERIFY(existing.open(QIODevice::WriteOnly)); existing.write("original destination"); existing.close();
        EngineJob job(engine); QSignalSpy done(&job, &EngineJob::finished); bool reachedEncoding = false;
        connect(&job, &EngineJob::eventReceived, &job, [&](const QJsonObject &event) {
            if (event["event"] == "stage" && event["stage"] == "encoding") { reachedEncoding = true; job.cancel(); }
        });
        job.start({"render", "--image", image, "--audio", longAudio, "--output", output, "--width", "1920", "--height", "1080"});
        QTRY_COMPARE_WITH_TIMEOUT(done.size(), 1, 30000); QVERIFY(reachedEncoding); QCOMPARE(done[0][0].toInt(), 130);
        QCOMPARE(contents(output), QByteArray("original destination"));
        const auto leftovers = QDir(media.path()).entryList(QDir::Files | QDir::Hidden);
        for (const auto &name : leftovers) {
            QVERIFY2(!name.contains(".ativ-"), qPrintable(name));
            QVERIFY2(!name.contains(".avid-"), qPrintable(name));
        }
    }
    void updateBoundary() {
#if defined(Q_OS_MACOS)
        QCOMPARE(UpdateClient::isSupported(), false);
#else
        QCOMPARE(UpdateClient::isSupported(), true);
#endif
    }
    void smokeReportGeneration() {
        const QString reportPath = media.filePath("smoke-report.json");
        qputenv("ATIV_SMOKE_REPORT", reportPath.toUtf8());
        MainWindow window(engine); QSignalSpy ready(&window, &MainWindow::presetsReady);
        window.show(); QTRY_COMPARE_WITH_TIMEOUT(ready.size(), 1, 10000);
        QVERIFY(QFile::exists(reportPath));
        const auto doc = QJsonDocument::fromJson(contents(reportPath));
        QVERIFY(doc.isObject());
        QCOMPARE(doc.object()["startup"].toBool(), true);
        QCOMPARE(doc.object()["presets"].toInt(), 27);
        qunsetenv("ATIV_SMOKE_REPORT");
        window.close(); QTRY_VERIFY_WITH_TIMEOUT(!window.isVisible(), 10000);
    }
};
QTEST_MAIN(WorkflowTests)
#include "tests.moc"
