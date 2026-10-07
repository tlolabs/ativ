// SPDX-License-Identifier: GPL-3.0-or-later
#include "Preferences.h"
#include <QCoreApplication>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonObject>
#include <QProcessEnvironment>
#include <QSaveFile>
#include <QStandardPaths>

bool Preferences::isDevelopmentBuild() {
    return QFile::exists(QCoreApplication::applicationDirPath() + "/development-build");
}

QString Preferences::folderPath() {
    const bool dev = isDevelopmentBuild();
#if defined(Q_OS_WIN)
    // Match standard Windows AppData/Local/ATIV location:
    const QString base = QStandardPaths::writableLocation(QStandardPaths::GenericDataLocation);
    return QDir(base).filePath(dev ? "ATIV Development" : "ATIV");
#elif defined(Q_OS_LINUX)
    const auto env = QProcessEnvironment::systemEnvironment();
    QString configHome = env.value("XDG_CONFIG_HOME");
    if (configHome.trimmed().isEmpty()) {
        configHome = QDir::homePath() + "/.config";
    }
    return QDir(configHome).filePath(dev ? "ativ-development" : "ativ");
#elif defined(Q_OS_MACOS)
    const QString appSupport = QStandardPaths::writableLocation(QStandardPaths::GenericDataLocation);
    return QDir(appSupport).filePath(dev ? "ATIV Development" : "ATIV Reference");
#else
    return QDir(QStandardPaths::writableLocation(QStandardPaths::AppConfigLocation)).path();
#endif
}

QString Preferences::filePath() {
    return QDir(folderPath()).filePath("preferences.json");
}

Preferences Preferences::loadLegacyLinux(const QString &iniPath) {
    Preferences result;
    QFile file(iniPath);
    if (!file.open(QIODevice::ReadOnly | QIODevice::Text)) {
        return result;
    }
    bool general = false;
    while (!file.atEnd()) {
        const QString line = QString::fromUtf8(file.readLine()).trimmed();
        if (line.startsWith('[')) {
            general = (line == "[General]");
            continue;
        }
        if (!general) continue;
        const int split = line.indexOf('=');
        if (split < 0) continue;
        const QString key = line.left(split).trimmed();
        const QString val = line.mid(split + 1).trimmed();
        if (key == "appearance") {
            const QString lower = val.toLower();
            if (lower == "dark") result.appearance = "Dark";
            else if (lower == "light") result.appearance = "Light";
            else result.appearance = "System";
        } else if (key == "bitrate") {
            result.bitrate = val;
        } else if (key == "fps") {
            bool ok = false;
            const int fpsVal = val.toInt(&ok);
            if (ok && fpsVal >= 1 && fpsVal <= 240) {
                result.fps = fpsVal;
            }
        } else if (key == "automatic_updates") {
            result.automaticUpdates = (val.compare("true", Qt::CaseInsensitive) == 0);
        }
    }
    return result;
}

Preferences Preferences::load() {
    Preferences prefs;
    const QString jsonPath = filePath();
    QFile file(jsonPath);
    if (file.open(QIODevice::ReadOnly)) {
        const auto doc = QJsonDocument::fromJson(file.readAll());
        if (doc.isObject()) {
            const auto obj = doc.object();
            if (obj.contains("Appearance")) prefs.appearance = obj["Appearance"].toString(prefs.appearance);
            else if (obj.contains("appearance")) prefs.appearance = obj["appearance"].toString(prefs.appearance);

            if (obj.contains("Bitrate")) prefs.bitrate = obj["Bitrate"].toString(prefs.bitrate);
            else if (obj.contains("bitrate")) prefs.bitrate = obj["bitrate"].toString(prefs.bitrate);

            if (obj.contains("Fps")) prefs.fps = qBound(1, obj["Fps"].toInt(prefs.fps), 240);
            else if (obj.contains("fps")) prefs.fps = qBound(1, obj["fps"].toInt(prefs.fps), 240);

            if (obj.contains("AutomaticUpdates")) prefs.automaticUpdates = obj["AutomaticUpdates"].toBool(prefs.automaticUpdates);
            else if (obj.contains("automatic_updates")) prefs.automaticUpdates = obj["automatic_updates"].toBool(prefs.automaticUpdates);
            return prefs;
        }
    }

#if defined(Q_OS_LINUX)
    const QString iniPath = QDir(folderPath()).filePath("preferences.ini");
    if (QFile::exists(iniPath)) {
        return loadLegacyLinux(iniPath);
    }
#endif

    return prefs;
}

bool Preferences::save() const {
    const QString folder = folderPath();
    QDir().mkpath(folder);
    const QString path = filePath();

    QJsonObject obj;
    obj["Appearance"] = appearance;
    obj["Bitrate"] = bitrate;
    obj["Fps"] = fps;
    obj["AutomaticUpdates"] = automaticUpdates;

    const QByteArray data = QJsonDocument(obj).toJson(QJsonDocument::Indented);
    QSaveFile file(path);
    if (!file.open(QIODevice::WriteOnly)) {
        return false;
    }
    file.write(data);
    return file.commit();
}
