// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "Preferences.h"
#include <QDialog>

class QComboBox;
class QSpinBox;
class QCheckBox;

class PreferencesDialog : public QDialog {
    Q_OBJECT
public:
    explicit PreferencesDialog(const Preferences &current, QWidget *parent = nullptr);
    Preferences preferences() const;

private:
    QComboBox *appearanceCombo;
    QComboBox *bitrateCombo;
    QSpinBox *fpsSpin;
    QCheckBox *autoUpdateCheck;
};
