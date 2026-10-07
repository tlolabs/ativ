// SPDX-License-Identifier: GPL-3.0-or-later
#include "EngineJob.h"
#include <QJsonDocument>
#include <QDebug>

EngineJob::EngineJob(QString enginePath, QObject *parent)
    : QObject(parent), engine(std::move(enginePath)) {
    connect(&process, &QProcess::readyReadStandardOutput, this, [this] { readOutput(); });
    connect(&process, &QProcess::readyReadStandardError, this, [this] {
        stderrTail = (stderrTail + process.readAllStandardError()).right(8192);
    });
    connect(&process, &QProcess::started, this, [this] {
        if (cancelled) process.write("cancel\n");
    });
    connect(&process, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) {
        if (error == QProcess::FailedToStart) {
            qWarning().noquote() << "ATIV media engine launch failed:" << process.errorString();
            failure = "The ATIV media engine could not start. Reinstall the complete application and try again.";
            complete(-1);
        }
    });
    connect(&process, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this,
            [this](int code, QProcess::ExitStatus status) {
        readOutput(true);
        stderrTail = (stderrTail + process.readAllStandardError()).right(8192);
        complete(status == QProcess::CrashExit ? -1 : code);
    });
    killDeadline.setSingleShot(true);
    connect(&killDeadline, &QTimer::timeout, this, [this] { if (active) process.kill(); });
    deadline.setSingleShot(true);
    connect(&deadline, &QTimer::timeout, this, [this] {
        failure = "The media operation timed out.";
        cancel();
        // Only read/preview operations have deadlines; never kill a render.
        killDeadline.start(3000);
    });
}

void EngineJob::start(const QStringList &arguments) {
    if (active) return;
    pending.clear(); stderrTail.clear(); failure.clear(); cancelled = false; active = true;
    process.setProgram(engine);
    process.setArguments(arguments);
    if (arguments.value(0) != "render") deadline.start(60000);
    process.start();
}

void EngineJob::cancel() {
    cancelled = true;
    if (process.state() == QProcess::Running) process.write("cancel\n");
}

void EngineJob::readOutput(bool flush) {
    pending += process.readAllStandardOutput();
    while (true) {
        auto end = pending.indexOf('\n');
        if (end < 0) {
            if (!flush || pending.isEmpty()) break;
            end = pending.size();
        }
        const auto line = pending.left(end);
        pending.remove(0, end + 1);
        QJsonParseError parseError;
        const auto document = QJsonDocument::fromJson(line, &parseError);
        if (parseError.error != QJsonParseError::NoError || !document.isObject()) {
            failure = "The media engine returned an invalid response.";
            continue;
        }
        const auto event = document.object();
        if (event["event"] == "error") failure = event["message"].toString();
        emit eventReceived(event);
    }
}

void EngineJob::complete(int code) {
    if (!active) return;
    deadline.stop(); killDeadline.stop(); active = false;
    if (code != 0 && failure.isEmpty()) {
        if (!stderrTail.isEmpty()) qWarning().noquote() << "ATIV media engine error:" << QString::fromUtf8(stderrTail);
        failure = "The media operation could not finish. Check the selected files and destination, then try again.";
    }
    if (code == 0 && !failure.isEmpty()) code = -1;
    emit finished(code, failure);
}
