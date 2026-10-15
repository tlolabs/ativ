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
    pending.clear(); discardingLine = false; stderrTail.clear(); failure.clear(); cancelled = false; active = true;
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
    consumeOutput(process.readAllStandardOutput(), flush);
}

void EngineJob::consumeOutput(const QByteArray &data, bool flush) {
    const auto parse = [this](const QByteArray &line) {
        QJsonParseError parseError;
        const auto document = QJsonDocument::fromJson(line, &parseError);
        if (parseError.error != QJsonParseError::NoError || !document.isObject()) {
            failure = "The media engine returned an invalid response.";
            return;
        }
        const auto event = document.object();
        if (event["event"] == "error") failure = event["message"].toString();
        emit eventReceived(event);
    };
    qsizetype start = 0;
    while (start < data.size()) {
        const auto newline = data.indexOf('\n', start);
        const auto end = newline < 0 ? data.size() : newline;
        const auto size = end - start;
        if (!discardingLine) {
            if (size > maximumLineBytes - pending.size()) {
                pending.clear();
                discardingLine = true;
                failure = "The media engine returned an invalid response.";
            } else if (pending.isEmpty() && newline >= 0) {
                parse(QByteArray::fromRawData(data.constData() + start, size));
            } else {
                pending.append(data.constData() + start, size);
                if (newline >= 0) {
                    // Clear framing state before invoking a UI callback.
                    const auto line = std::move(pending);
                    pending.clear();
                    parse(line);
                }
            }
        }
        if (newline < 0) break;
        discardingLine = false;
        start = newline + 1;
    }
    if (flush) {
        const auto line = std::move(pending);
        pending.clear();
        if (!discardingLine && !line.isEmpty()) parse(line);
        discardingLine = false;
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
