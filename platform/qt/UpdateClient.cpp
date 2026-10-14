// SPDX-License-Identifier: GPL-3.0-or-later
#include "UpdateClient.h"
#include <QCoreApplication>
#include <QDesktopServices>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonObject>
#include <QProcess>
#include <QTimer>
#include <QUrl>
#include <QUuid>
#include <memory>

UpdateClient::UpdateClient(QObject *parent) : QObject(parent) {}

bool UpdateClient::isSupported() {
    if (qEnvironmentVariableIsSet("ATIV_TEST_UPDATE_SUPPORTED")) {
        return true;
    }
#if defined(Q_OS_MACOS)
    // macOS reference build must never enter production update channel.
    return false;
#else
    return true;
#endif
}

bool UpdateClient::canInstallDirectly() {
    if (qEnvironmentVariableIsSet("ATIV_TEST_UPDATE_SUPPORTED")) {
        return true;
    }
#if defined(Q_OS_WIN)
    return true;
#elif defined(Q_OS_LINUX)
    return !qEnvironmentVariableIsEmpty("APPIMAGE");
#else
    return false;
#endif
}

QString UpdateClient::updateBinaryPath() {
    const QString configured = qEnvironmentVariable("ATIV_UPDATE_PATH");
    if (!configured.isEmpty() && QFile::exists(configured)) {
        return configured;
    }
#if defined(Q_OS_WIN)
    const QString binary = QCoreApplication::applicationDirPath() + "/ativ-update.exe";
#else
    const QString binary = QCoreApplication::applicationDirPath() + "/ativ-update";
#endif
    return binary;
}

static void runProcessSafely(QObject *parent,
                             bool &busyFlag,
                             const QString &program,
                             const QStringList &args,
                             int timeoutMs,
                             const QString &timeoutMsg,
                             std::function<void(int exitCode,
                                                QProcess::ExitStatus exitStatus,
                                                QProcess::ProcessError error,
                                                const QByteArray &stdoutData,
                                                const QByteArray &stderrData,
                                                const QString &customError)> onResult) {
    auto *process = new QProcess(parent);
    process->setProgram(program);
    process->setArguments(args);

    auto *timer = new QTimer(process);
    timer->setSingleShot(true);

    auto invoked = std::make_shared<bool>(false);

    auto finish = [&busyFlag, process, timer, invoked, onResult](int exitCode,
                                                                 QProcess::ExitStatus exitStatus,
                                                                 QProcess::ProcessError error,
                                                                 const QByteArray &stdoutData,
                                                                 const QByteArray &stderrData,
                                                                 const QString &customError) {
        if (*invoked) return;
        *invoked = true;
        busyFlag = false;

        timer->stop();
        if (process->state() != QProcess::NotRunning) {
            process->kill();
            process->waitForFinished(500);
        }
        process->deleteLater();

        onResult(exitCode, exitStatus, error, stdoutData, stderrData, customError);
    };

    QObject::connect(timer, &QTimer::timeout, process, [finish, timeoutMsg]() {
        finish(-1, QProcess::CrashExit, QProcess::Timedout, {}, {}, timeoutMsg);
    });

    QObject::connect(process, &QProcess::errorOccurred, process, [finish](QProcess::ProcessError err) {
        if (err == QProcess::FailedToStart) {
            finish(-1, QProcess::NormalExit, err, {}, {}, "The update helper failed to start.");
        } else if (err == QProcess::Crashed) {
            finish(-1, QProcess::CrashExit, err, {}, {}, "The update helper crashed unexpectedly.");
        } else if (err == QProcess::Timedout) {
            finish(-1, QProcess::CrashExit, err, {}, {}, "The update operation timed out.");
        }
    });

    QObject::connect(process, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), process,
                     [process, finish](int code, QProcess::ExitStatus status) {
        const QByteArray stdoutData = process->readAllStandardOutput();
        const QByteArray stderrData = process->readAllStandardError();
        finish(code, status, QProcess::UnknownError, stdoutData, stderrData, QString());
    });

    timer->start(timeoutMs);
    process->start();
}

void UpdateClient::checkForUpdates(bool manual, std::function<void(bool available, const QString &version, const QString &error)> callback) {
    if (!isSupported()) {
        callback(false, {}, "Automatic updates are unavailable in the internal reference build.");
        return;
    }
    if (busy) {
        callback(false, {}, "An update operation is already in progress.");
        return;
    }

    const QString binary = updateBinaryPath();
    if (!QFile::exists(binary)) {
        callback(false, {}, "The update component is missing.");
        return;
    }

    busy = true;
    const int timeoutMs = qEnvironmentVariableIntValue("ATIV_UPDATE_TIMEOUT_MS") > 0
        ? qEnvironmentVariableIntValue("ATIV_UPDATE_TIMEOUT_MS")
        : 60000;

    runProcessSafely(this, busy, binary, {manual ? "check" : "check-auto"}, timeoutMs,
                     "Update check timed out.",
                     [callback](int code, QProcess::ExitStatus status, QProcess::ProcessError error,
                                const QByteArray &stdoutData, const QByteArray &stderrData,
                                const QString &customError) {
        if (!customError.isEmpty()) {
            callback(false, {}, customError);
            return;
        }
        if (status == QProcess::CrashExit || error == QProcess::Crashed) {
            callback(false, {}, "The update helper crashed unexpectedly.");
            return;
        }
        if (code != 0) {
            callback(false, {}, stderrData.isEmpty() ? "Update check failed." : QString::fromUtf8(stderrData).trimmed());
            return;
        }

        const auto doc = QJsonDocument::fromJson(stdoutData);
        if (!doc.isObject()) {
            callback(false, {}, "The update service returned an invalid response.");
            return;
        }

        const auto obj = doc.object();
        const bool available = obj["available"].toBool(false);
        const QString version = obj["version"].toString();
        callback(available, version, QString());
    });
}

void UpdateClient::installOrDownload(QWidget * /*parent*/, std::function<void(bool success, const QString &message)> callback) {
    if (!isSupported()) {
        callback(false, "Automatic updates are unavailable in the internal reference build.");
        return;
    }
    if (busy) {
        callback(false, "An update operation is already in progress.");
        return;
    }

    const QString binary = updateBinaryPath();
    if (!QFile::exists(binary)) {
        callback(false, "The update component is missing.");
        return;
    }

    busy = true;
#if defined(Q_OS_WIN) || defined(Q_OS_LINUX)
    const int timeoutMs = qEnvironmentVariableIntValue("ATIV_UPDATE_TIMEOUT_MS") > 0
        ? qEnvironmentVariableIntValue("ATIV_UPDATE_TIMEOUT_MS")
        : 300000;
#endif

#if defined(Q_OS_WIN)
    runProcessSafely(this, busy, binary, {"download"}, timeoutMs,
                     "Update download timed out.",
                     [this, callback](int code, QProcess::ExitStatus status, QProcess::ProcessError error,
                                      const QByteArray &stdoutData, const QByteArray &stderrData,
                                      const QString &customError) {
        if (!customError.isEmpty()) {
            callback(false, customError);
            return;
        }
        if (status == QProcess::CrashExit || error == QProcess::Crashed) {
            callback(false, "The update helper crashed unexpectedly.");
            return;
        }
        if (code != 0) {
            callback(false, stderrData.isEmpty() ? "Could not download update." : QString::fromUtf8(stderrData).trimmed());
            return;
        }

        const auto doc = QJsonDocument::fromJson(stdoutData);
        if (!doc.isObject()) {
            callback(false, "The update service returned an invalid response.");
            return;
        }

        const auto obj = doc.object();
        const QString downloadPath = obj["path"].toString();
        const QString sha256 = obj["sha256"].toString();
        const QString target = obj["target"].toString();
        const QString version = obj["version"].toString();

        const QString tempDir = QDir::tempPath() + "/ativ-portable-helper-" + QUuid::createUuid().toString(QUuid::WithoutBraces);
        QDir().mkpath(tempDir);
        const QString helperSrc = QCoreApplication::applicationDirPath() + "/ativ-portable-update.exe";
        const QString helperDest = tempDir + "/ativ-portable-update.exe";

        if (!QFile::copy(helperSrc, helperDest)) {
            callback(false, "Could not stage the portable update helper.");
            return;
        }

        QStringList args;
        args << downloadPath << sha256 << QDir::toNativeSeparators(QCoreApplication::applicationDirPath())
             << QString::number(QCoreApplication::applicationPid()) << target << version;

        if (!QProcess::startDetached(helperDest, args)) {
            callback(false, "Could not start the portable update helper.");
            return;
        }

        callback(true, "Installation started. ATIV will close to complete the update.");
        QCoreApplication::quit();
    });

#elif defined(Q_OS_LINUX)
    if (canInstallDirectly()) {
        runProcessSafely(this, busy, binary, {"install-appimage"}, timeoutMs,
                         "AppImage installation timed out.",
                         [callback](int code, QProcess::ExitStatus status, QProcess::ProcessError error,
                                    const QByteArray &/*stdoutData*/, const QByteArray &stderrData,
                                    const QString &customError) {
            if (!customError.isEmpty()) {
                callback(false, customError);
                return;
            }
            if (status == QProcess::CrashExit || error == QProcess::Crashed) {
                callback(false, "The update helper crashed unexpectedly.");
                return;
            }
            if (code != 0) {
                callback(false, stderrData.isEmpty() ? "AppImage installation failed." : QString::fromUtf8(stderrData).trimmed());
                return;
            }
            callback(true, "Update installed. Restart ATIV to use the new version.");
        });
    } else {
        runProcessSafely(this, busy, binary, {"download"}, timeoutMs,
                         "Update download timed out.",
                         [callback](int code, QProcess::ExitStatus status, QProcess::ProcessError error,
                                    const QByteArray &stdoutData, const QByteArray &stderrData,
                                    const QString &customError) {
            if (!customError.isEmpty()) {
                callback(false, customError);
                return;
            }
            if (status == QProcess::CrashExit || error == QProcess::Crashed) {
                callback(false, "The update helper crashed unexpectedly.");
                return;
            }
            if (code != 0) {
                callback(false, stderrData.isEmpty() ? "Could not download update." : QString::fromUtf8(stderrData).trimmed());
                return;
            }

            const auto doc = QJsonDocument::fromJson(stdoutData);
            if (!doc.isObject()) {
                callback(false, "The update service returned an invalid response.");
                return;
            }

            const QString downloadPath = doc.object()["path"].toString();
            const QString folder = QFileInfo(downloadPath).absolutePath();
            QDesktopServices::openUrl(QUrl::fromLocalFile(folder));
            callback(true, "Verified update downloaded. Close ATIV and replace the old binary manually.");
        });
    }
#else
    busy = false;
    callback(false, "Updates are unsupported on this platform.");
#endif
}
