// SPDX-License-Identifier: GPL-3.0-or-later
#include "MainWindow.h"
#include <QAccessible>
#include <QApplication>
#include <QLabel>
#include <QLineEdit>
#include <QProgressBar>
#include <QScrollArea>
#include <QScrollBar>
#include <QCheckBox>
#include <QComboBox>
#include <QMenuBar>
#include <QPushButton>
#include <QSpinBox>
#include <QShortcut>
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

    void interactiveControlsHaveAccessibleNamesAndTooltips() {
        MainWindow window("/missing/ativ-engine");
        auto *create = window.findChild<QPushButton *>("createVideo");
        auto *cancel = window.findChild<QPushButton *>("cancelRender");
        auto *flipH = window.findChild<QCheckBox *>("flipHorizontal");
        auto *flipV = window.findChild<QCheckBox *>("flipVertical");
        auto *platform = window.findChild<QComboBox *>("platform");
        auto *aspect = window.findChild<QComboBox *>("aspect");
        auto *resolution = window.findChild<QComboBox *>("resolution");
        auto *fps = window.findChild<QSpinBox *>("fps");
        auto *image = window.findChild<QLineEdit *>("imagePath");
        auto *audio = window.findChild<QLineEdit *>("audioPath");
        auto *output = window.findChild<QLineEdit *>("outputPath");
        auto *chooseImg = window.findChild<QPushButton *>("choose_imagePath");
        auto *chooseAud = window.findChild<QPushButton *>("choose_audioPath");
        auto *chooseOut = window.findChild<QPushButton *>("choose_outputPath");

        QVERIFY(create && !create->accessibleName().isEmpty() && !create->toolTip().isEmpty());
        QVERIFY(cancel && !cancel->accessibleName().isEmpty() && !cancel->toolTip().isEmpty());
        QVERIFY(flipH && !flipH->accessibleName().isEmpty() && !flipH->toolTip().isEmpty());
        QVERIFY(flipV && !flipV->accessibleName().isEmpty() && !flipV->toolTip().isEmpty());
        QVERIFY(platform && !platform->accessibleName().isEmpty() && !platform->toolTip().isEmpty());
        QVERIFY(aspect && !aspect->accessibleName().isEmpty() && !aspect->toolTip().isEmpty());
        QVERIFY(resolution && !resolution->accessibleName().isEmpty() && !resolution->toolTip().isEmpty());
        QVERIFY(fps && !fps->accessibleName().isEmpty() && !fps->toolTip().isEmpty());
        QVERIFY(image && !image->accessibleName().isEmpty() && !image->toolTip().isEmpty());
        QVERIFY(audio && !audio->accessibleName().isEmpty() && !audio->toolTip().isEmpty());
        QVERIFY(output && !output->accessibleName().isEmpty() && !output->toolTip().isEmpty());
        QVERIFY(chooseImg && !chooseImg->accessibleName().isEmpty() && !chooseImg->toolTip().isEmpty());
        QVERIFY(chooseAud && !chooseAud->accessibleName().isEmpty() && !chooseAud->toolTip().isEmpty());
        QVERIFY(chooseOut && !chooseOut->accessibleName().isEmpty() && !chooseOut->toolTip().isEmpty());
    }

    void keyboardShortcutsAndMenuMnemonics() {
        MainWindow window("/missing/ativ-engine");
        auto *create = window.findChild<QPushButton *>("createVideo");
        auto *cancel = window.findChild<QPushButton *>("cancelRender");
        QVERIFY(create);
        QVERIFY(cancel);

        // Escape cancels
        QCOMPARE(cancel->shortcut(), QKeySequence(Qt::Key_Escape));

        // Create supports Ctrl+Return and Ctrl+Enter
        QCOMPARE(create->shortcut(), QKeySequence(Qt::CTRL | Qt::Key_Return));
        bool foundEnterShortcut = false;
        for (auto *sc : window.findChildren<QShortcut *>()) {
            if (sc->key() == QKeySequence(Qt::CTRL | Qt::Key_Enter)) foundEnterShortcut = true;
        }
        QVERIFY(foundEnterShortcut);

        // Menus have mnemonics
        auto *menuBar = window.menuBar();
        QVERIFY(menuBar);
        bool foundFile = false, foundSettings = false, foundHelp = false;
        for (auto *action : menuBar->actions()) {
            if (action->text().contains("&File")) foundFile = true;
            if (action->text().contains("&Settings")) foundSettings = true;
            if (action->text().contains("&Help")) foundHelp = true;
        }
        QVERIFY(foundFile);
        QVERIFY(foundSettings);
        QVERIFY(foundHelp);
    }

    void appearanceSwitchingAppliesThemes() {
        MainWindow window("/missing/ativ-engine");
        // Dark theme palette
        window.applyAppearance("Dark");
        QCOMPARE(qApp->palette().color(QPalette::Window), QColor(40, 42, 48));
        QCOMPARE(qApp->palette().color(QPalette::WindowText), QColor(Qt::white));
        QVERIFY(qApp->palette().color(QPalette::ToolTipBase) != qApp->palette().color(QPalette::ToolTipText));

        // Light theme palette
        window.applyAppearance("Light");
        QVERIFY(qApp->palette().color(QPalette::Window).lightness() > 100);

        // System theme
        window.applyAppearance("System");
    }
};

QTEST_MAIN(AccessibilityTests)
#include "accessibility_tests.moc"
