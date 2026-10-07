// SPDX-License-Identifier: GPL-3.0-or-later
#include "MainWindow.h"
#include <QApplication>
#include <QIcon>
#include <QFile>

int main(int argc, char **argv) {
    QApplication app(argc, argv);
#if defined(Q_OS_MACOS)
    app.setApplicationName("ATIV Qt");
#else
    app.setApplicationName("ATIV");
#endif
    app.setApplicationVersion("0.2.6");
    app.setOrganizationName("TLO Labs");
    app.setOrganizationDomain("tlolabs.com");

#if defined(Q_OS_WIN)
    const QString winIcon = QCoreApplication::applicationDirPath() + "/Assets/ATIV.ico";
    if (QFile::exists(winIcon)) {
        app.setWindowIcon(QIcon(winIcon));
    }
#elif defined(Q_OS_LINUX)
    const QString linuxIcon = QCoreApplication::applicationDirPath() + "/../share/icons/hicolor/256x256/apps/com.tlolabs.ativ.png";
    if (QFile::exists(linuxIcon)) {
        app.setWindowIcon(QIcon(linuxIcon));
    }
#endif

    MainWindow window;
    window.show();
    return app.exec();
}
