// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <QString>

class Preferences {
public:
    QString appearance = "System";
    QString bitrate = "128k";
    int fps = 30;
    bool automaticUpdates = true;

    static QString folderPath();
    static QString filePath();
    static Preferences load();
    bool save() const;

    static Preferences loadLegacyLinux(const QString &iniPath);
    static bool isDevelopmentBuild();
};
