// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <QJsonObject>
#include <QProcess>
#include <QTimer>

// One operation per instance; all I/O is asynchronous on the UI event loop.
class EngineJob : public QObject {
    Q_OBJECT
public:
    explicit EngineJob(QString enginePath, QObject *parent = nullptr);
    bool busy() const { return active; }
    void start(const QStringList &arguments);
    void cancel();
signals:
    void eventReceived(const QJsonObject &event);
    void finished(int exitCode, const QString &error);
private:
    void readOutput(bool flush = false);
    void complete(int code);
    QString engine;
    QProcess process;
    QTimer deadline, killDeadline;
    QByteArray pending, stderrTail;
    QString failure;
    bool active = false, cancelled = false;
};
