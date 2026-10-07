// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <QObject>
#include <QString>
#include <functional>

class QWidget;

class UpdateClient : public QObject {
    Q_OBJECT
public:
    explicit UpdateClient(QObject *parent = nullptr);

    static bool isSupported();
    static bool canInstallDirectly();

    void checkForUpdates(bool manual, std::function<void(bool available, const QString &version, const QString &error)> callback);
    void installOrDownload(QWidget *parent, std::function<void(bool success, const QString &message)> callback);

private:
    static QString updateBinaryPath();
    bool busy = false;
};
