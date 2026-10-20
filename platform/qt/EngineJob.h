// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <QJsonObject>
#include <QProcess>
#include <QPointer>
#include <QList>
#include <QTimer>

// One operation per instance; all I/O is asynchronous on the UI event loop.
class EngineJob : public QObject {
    Q_OBJECT
public:
    explicit EngineJob(QString enginePath, QObject *parent = nullptr);
    ~EngineJob() override;
    bool busy() const { return active; }
    void start(const QStringList &arguments);
    void cancel();
signals:
    void eventReceived(const QJsonObject &event);
    void finished(int exitCode, const QString &error);
private:
    friend class WorkflowTests;
    void readOutput(bool flush = false);
    void consumeOutput(const QByteArray &data, bool flush = false);
    static constexpr qsizetype maximumLineBytes = 8 * 1024 * 1024;
    bool discardingLine = false;
    void complete(int code);
    static void startNext();
    static QList<QPointer<EngineJob>> waiting;
    static bool workerActive;
    QStringList queuedArguments;
    bool ownsWorker = false, published = false;
    QString engine;
    QProcess process;
    QTimer deadline, killDeadline;
    QByteArray pending, stderrTail;
    QString failure;
    bool active = false, cancelled = false;
};
