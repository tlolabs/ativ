// SPDX-License-Identifier: GPL-3.0-or-later
#include "MainWindow.h"
#include <QAccessible>
#include <QApplication>
#include <QLabel>
#include <QLineEdit>
#include <QProgressBar>
#include <QScrollArea>
#include <QScrollBar>
#include <QtTest>

class AccessibilityTests : public QObject {
    Q_OBJECT
private slots:
    void compactWindowKeepsDestinationReachable() {
        MainWindow window("/missing/ativ-engine");
        QFont large = window.font();
        large.setPointSize(qMax(18, large.pointSize()));
        window.setFont(large);
        window.resize(640, 480);
        window.show();
        QCoreApplication::processEvents();

        auto *scroll = window.findChild<QScrollArea *>();
        auto *destination = window.findChild<QLineEdit *>("outputPath");
        QVERIFY(scroll);
        QVERIFY(destination);
        QVERIFY(scroll->verticalScrollBar()->maximum() > 0);
        scroll->ensureWidgetVisible(destination);
        QCoreApplication::processEvents();
        const QPoint center = destination->mapTo(scroll->viewport(), destination->rect().center());
        QVERIFY(scroll->viewport()->rect().contains(center));
    }

    void statusAndProgressExposeCurrentInformation() {
        MainWindow window("/missing/ativ-engine");
        auto *status = window.findChild<QLabel *>("status");
        auto *progress = window.findChild<QProgressBar *>();
        QVERIFY(status);
        QVERIFY(progress);
        auto *statusInterface = QAccessible::queryAccessibleInterface(status);
        QVERIFY(statusInterface);
        QCOMPARE(statusInterface->text(QAccessible::Name), status->text());
        QCOMPARE(progress->accessibleName(), QString("Video creation progress"));
        QVERIFY(progress->isTextVisible());
    }
};

QTEST_MAIN(AccessibilityTests)
#include "accessibility_tests.moc"
