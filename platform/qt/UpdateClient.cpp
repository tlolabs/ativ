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
#include <QUrl>
#include <QUuid>

UpdateClient::UpdateClient(QObject *parent) : QObject(parent) {}

bool UpdateClient::isSupported() {
#if defined(Q_OS_MACOS)
    // macOS reference build must never enter production update channel.
    return false;
#else
    return true;
#endif
}

bool UpdateClient::canInstallDirectly() {
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
    auto *process = new QProcess(this);
    process->setProgram(binary);
    process->setArguments({manual ? "check" : "check-auto"});

    connect(process, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this,
            [this, process, callback](int code, QProcess::ExitStatus) {
        busy = false;
        const QByteArray stdoutData = process->readAllStandardOutput();
        const QByteArray stderrData = process->readAllStandardError();
        process->deleteLater();

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

    process->start();
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

#if defined(Q_OS_WIN)
    auto *process = new QProcess(this);
    process->setProgram(binary);
    process->setArguments({"download"});

    connect(process, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this,
            [this, process, callback](int code, QProcess::ExitStatus) {
        busy = false;
        const QByteArray stdoutData = process->readAllStandardOutput();
        const QByteArray stderrData = process->readAllStandardError();
        process->deleteLater();

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

    process->start();

#elif defined(Q_OS_LINUX)
    if (canInstallDirectly()) {
        auto *process = new QProcess(this);
        process->setProgram(binary);
        process->setArguments({"install-appimage"});

        connect(process, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this,
                [this, process, callback](int code, QProcess::ExitStatus) {
            busy = false;
            const QByteArray stderrData = process->readAllStandardError();
            process->deleteLater();

            if (code != 0) {
                callback(false, stderrData.isEmpty() ? "AppImage installation failed." : QString::fromUtf8(stderrData).trimmed());
                return;
            }
            callback(true, "Update installed. Restart ATIV to use the new version.");
        });

        process->start();
    } else {
        auto *process = new QProcess(this);
        process->setProgram(binary);
        process->setArguments({"download"});

        connect(process, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this,
                [this, process, callback](int code, QProcess::ExitStatus) {
            busy = false;
            const QByteArray stdoutData = process->readAllStandardOutput();
            const QByteArray stderrData = process->readAllStandardError();
            process->deleteLater();

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

        process->start();
    }
#else
    busy = false;
    callback(false, "Updates are unsupported on this platform.");
#endif
}
